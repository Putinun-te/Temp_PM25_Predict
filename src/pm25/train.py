"""Train, evaluate and promote the forecasting methods.

Every target and horizon is a slot with its own method. A slot publishes a
fitted model only if that model earned it. Otherwise it publishes the best
naive baseline, which is an honest answer when the model adds nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from pm25.evaluate import (
    metrics,
    monthly_walk_forward,
    promotion_gate,
    residual_q80,
    season_errors,
    skill,
    walk_forward_predict,
)
from pm25.features import (
    TARGETS,
    build_features,
    build_labels,
    daily_baselines,
    monthly_targets,
)

DAILY_HORIZONS = (1, 2)
MONTHLY_HORIZONS = (2, 3, 4)  # From the last complete month to one, two and three months ahead
LATEST_WINDOW_DAYS = 90
MIN_UNSEEN_DAYS = 14
REGISTRY_FILENAME = "registry.json"
METRICS_FILENAME = "metrics.json"
PLOT_FILENAME = "walk_forward.png"


class DropEmptyColumns(BaseEstimator, TransformerMixin):
    """Remove columns with no values in the training data.

    Open-Meteo history starts later than the station history, so early
    walk-forward folds have feature columns that are entirely missing.
    """

    def fit(self, features: Any, labels: Any = None) -> "DropEmptyColumns":
        self.keep_ = ~np.isnan(np.asarray(features, dtype=float)).all(axis=0)
        return self

    def transform(self, features: Any) -> np.ndarray:
        return np.asarray(features, dtype=float)[:, self.keep_]


def _gradient_boosting() -> Any:
    return make_pipeline(
        DropEmptyColumns(),
        HistGradientBoostingRegressor(
            max_iter=200,
            learning_rate=0.05,
            max_leaf_nodes=15,
            min_samples_leaf=20,
            l2_regularization=1.0,
            random_state=0,
        ),
    )


def _random_forest() -> Any:
    return make_pipeline(
        DropEmptyColumns(),
        SimpleImputer(strategy="median"),
        RandomForestRegressor(
            n_estimators=150, min_samples_leaf=3, max_features=0.5, n_jobs=-1, random_state=0
        ),
    )


CANDIDATES = {"gradient_boosting": _gradient_boosting, "random_forest": _random_forest}


def model_path(models_dir: Path, slot: str) -> Path:
    return models_dir / f"{slot}.joblib"


def load_registry(models_dir: Path) -> dict[str, Any]:
    path = models_dir / REGISTRY_FILENAME
    if not path.exists():
        return {"daily": {}, "monthly": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def train_slot(
    target: str,
    horizon: int,
    features: pd.DataFrame,
    labels: pd.Series,
    baselines: dict[str, pd.Series],
    previous: dict[str, Any] | None,
    models_dir: Path,
    now: str,
    reference: pd.Series | None = None,
) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    """Evaluate one slot and return its registry entry, report and out-of-sample frame."""
    slot = f"{target}_h{horizon}"
    predictions = {
        name: walk_forward_predict(features, labels, factory, horizon)
        for name, factory in CANDIDATES.items()
    }
    frame = pd.DataFrame({"actual": labels, **predictions, **baselines}).dropna()
    if frame.empty:
        raise ValueError(f"{slot}: no rows to evaluate")

    methods = [*CANDIDATES, *baselines]
    overall = {name: metrics(frame["actual"], frame[name]) for name in methods}
    candidate = min(CANDIDATES, key=lambda name: overall[name]["mae"])
    latest = frame[frame.index > frame.index.max() - pd.Timedelta(days=LATEST_WINDOW_DAYS)]

    known = labels.notna().to_numpy()
    final_model = CANDIDATES[candidate]()
    final_model.fit(features[known], labels[known])
    train_end = (features.index[known].max() + pd.Timedelta(days=horizon)).date().isoformat()

    entry, promote = _decide(
        slot, candidate, latest, list(baselines), previous, features, models_dir, horizon
    )
    if promote:
        # A short recent window can favour a model by luck, so the full history must agree.
        overall_ok, overall_reason = promotion_gate(
            overall[candidate]["mae"], {name: overall[name]["mae"] for name in baselines}
        )
        if not overall_ok:
            promote = False
            entry = _fallback(previous, overall, list(baselines), f"over all folds it {overall_reason}")
    if promote:
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(final_model, model_path(models_dir, slot))
        entry.update({"method": candidate, "train_end": train_end, "promoted_at": now})

    entry["residual_q80"] = residual_q80(frame["actual"], frame[entry["method"]])
    report: dict[str, Any] = {
        "published_method": entry["method"],
        "decision": entry["reason"],
        "best_candidate": candidate,
        "overall": overall,
        "skill_vs_persistence": skill(overall[candidate]["mae"], overall["persistence"]["mae"]),
        "latest_window": {
            name: metrics(latest["actual"], latest[name]) for name in methods
        },
        "by_season": season_errors(frame, methods, horizon),
    }
    if reference is not None:
        paired = pd.DataFrame({"actual": frame["actual"], "cams": reference}).dropna()
        report["cams_hindsight_not_a_forecast"] = metrics(paired["actual"], paired["cams"])
    return entry, report, frame


def _fallback(
    previous: dict[str, Any] | None,
    overall: dict[str, dict[str, float]],
    baseline_names: list[str],
    why: str,
) -> dict[str, Any]:
    """Keep the previous model if there is one, otherwise use the best baseline."""
    if previous and previous["method"] in CANDIDATES:
        kept = dict(previous)
        kept["reason"] = f"kept: candidate rejected, {why}"
        return kept
    best = min(baseline_names, key=lambda name: overall[name]["mae"])
    return {"method": best, "reason": f"baseline used: {why}"}


def _decide(
    slot: str,
    candidate: str,
    latest: pd.DataFrame,
    baseline_names: list[str],
    previous: dict[str, Any] | None,
    features: pd.DataFrame,
    models_dir: Path,
    horizon: int,
) -> tuple[dict[str, Any], bool]:
    """Apply the promotion gate on the latest walk-forward window."""
    window = latest
    previous_mae = None
    has_previous_model = bool(previous) and previous["method"] in CANDIDATES

    if has_previous_model:
        # The previous model trained on data up to train_end. Only later rows are a fair test.
        cutoff = pd.Timestamp(previous["train_end"])
        window = latest[latest.index + pd.Timedelta(days=horizon) > cutoff]
        if len(window) < MIN_UNSEEN_DAYS:
            kept = dict(previous)
            kept["reason"] = f"kept: only {len(window)} days are unseen by the current model"
            return kept, False
        current_model = joblib.load(model_path(models_dir, slot))
        predicted = current_model.predict(features.loc[window.index])
        previous_mae = float(np.abs(window["actual"].to_numpy() - predicted).mean())

    candidate_mae = float((window["actual"] - window[candidate]).abs().mean())
    baseline_maes = {
        name: float((window["actual"] - window[name]).abs().mean()) for name in baseline_names
    }
    promote, reason = promotion_gate(candidate_mae, baseline_maes, previous_mae)
    if promote:
        return {"reason": f"promoted: {reason}"}, True
    if has_previous_model:
        kept = dict(previous)
        kept["reason"] = f"kept: candidate {reason}"
        return kept, False
    best_baseline = min(baseline_maes, key=baseline_maes.get)
    return {"method": best_baseline, "reason": f"baseline used: candidate {reason}"}, False


def train_monthly(series: pd.Series, horizon: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Choose the monthly method. The anomaly method must beat climatology to be used."""
    frame = monthly_walk_forward(series, horizon).dropna(
        subset=["actual", "climatology", "anomaly"]
    )
    if frame.empty:
        return (
            {"method": "climatology", "reason": "not enough history to compare", "residual_q80": None},
            {"published_method": "climatology", "n": 0},
        )
    report = {
        name: metrics(frame["actual"], frame[name]) for name in ("climatology", "anomaly")
    }
    last_year = frame.dropna(subset=["last_year"])
    if not last_year.empty:
        report["last_year"] = metrics(last_year["actual"], last_year["last_year"])
    promote, reason = promotion_gate(
        report["anomaly"]["mae"], {"climatology": report["climatology"]["mae"]}
    )
    method = "anomaly" if promote else "climatology"
    entry = {
        "method": method,
        "reason": reason,
        "residual_q80": residual_q80(frame["actual"], frame[method]),
    }
    return entry, {"published_method": method, "decision": reason, "n": int(len(frame)), **report}


def _save_plot(frame: pd.DataFrame, method: str, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    recent = frame[frame.index > frame.index.max() - pd.Timedelta(days=365)]
    # A daily calendar leaves missing days empty, so lines break instead of bridging gaps.
    recent = recent.asfreq("D")
    figure, axis = plt.subplots(figsize=(11, 4), layout="constrained")
    axis.plot(recent.index, recent["actual"], color="#222222", linewidth=1.4, label="Measured")
    axis.plot(
        recent.index,
        recent[method],
        color="#d1495b",
        linewidth=1.2,
        label=method.replace("_", " ").capitalize(),
    )
    axis.plot(
        recent.index, recent["persistence"], color="#8d99ae", linewidth=0.9, label="Persistence"
    )
    axis.set_title("PM2.5 tomorrow, out-of-sample walk-forward predictions")
    axis.set_ylabel("PM2.5 (µg/m³)")
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, ncols=3, loc="upper center")
    figure.savefig(path, dpi=130)
    plt.close(figure)


def run_training(
    targets: pd.DataFrame,
    exogenous: pd.DataFrame,
    models_dir: Path,
    now: str,
    as_of: pd.Timestamp,
) -> dict[str, Any]:
    """Evaluate every slot, update the registry and write metrics.json and a plot."""
    models_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(models_dir)
    report: dict[str, Any] = {
        "generated_at": now,
        "as_of": as_of.date().isoformat(),
        "data": {
            target: {
                "first_day": targets[target].first_valid_index().date().isoformat(),
                "last_day": targets[target].last_valid_index().date().isoformat(),
                "valid_days": int(targets[target].notna().sum()),
            }
            for target in TARGETS
        },
        "daily": {},
        "monthly": {},
    }

    plot_frame = None
    plot_method = None
    for target in TARGETS:
        for horizon in DAILY_HORIZONS:
            slot = f"{target}_h{horizon}"
            features = build_features(targets, exogenous, horizon)
            labels = build_labels(targets, horizon)[target]
            reference = None
            if target == "pm25":
                reference = exogenous["om_pm25"].reindex(targets.index).shift(-horizon)
            entry, slot_report, frame = train_slot(
                target,
                horizon,
                features,
                labels,
                daily_baselines(targets[target], horizon),
                registry["daily"].get(slot),
                models_dir,
                now,
                reference,
            )
            registry["daily"][slot] = entry
            report["daily"][slot] = slot_report
            if slot == "pm25_h2":
                # Plot the best model against persistence even when persistence is published.
                plot_frame, plot_method = frame, slot_report["best_candidate"]

    monthly = monthly_targets(targets)
    for target in TARGETS:
        for horizon in MONTHLY_HORIZONS:
            slot = f"{target}_m{horizon}"
            entry, slot_report = train_monthly(monthly[target], horizon)
            registry["monthly"][slot] = entry
            report["monthly"][slot] = slot_report

    (models_dir / REGISTRY_FILENAME).write_text(
        json.dumps(registry, indent=2) + "\n", encoding="utf-8"
    )
    (models_dir / METRICS_FILENAME).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    _save_plot(plot_frame, plot_method, models_dir / PLOT_FILENAME)
    return report
