"""Train, evaluate and promote the forecasting methods.

Every target and horizon is a slot with its own method. A slot publishes a
fitted model only if that model earned it. Otherwise it publishes the best
naive baseline, which is an honest answer when the model adds nothing.
"""

from __future__ import annotations

import json
from functools import partial
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
    range_entry,
    residual_q80,
    season_errors,
    skill,
    walk_forward_predict,
)
from pm25.transform import BlendWithWeekMean, ChangeFromLast, DropEmptyColumns, blend_with_week_mean  # noqa: F401  (saved models refer to pm25.train.DropEmptyColumns)
from pm25.features import (
    ALL_TARGETS,
    build_features,
    build_labels,
    model_inputs,
    daily_baselines,
    monthly_targets,
    with_weather_targets,
)

DAILY_HORIZONS = tuple(range(1, 8))  # Today and the six days after it
MONTHLY_HORIZONS = (2, 3, 4)  # From the last complete month to one, two and three months ahead
LATEST_WINDOW_DAYS = 90
MIN_UNSEEN_DAYS = 14
WAITING_REASON = "kept: only"
REGISTRY_FILENAME = "registry.json"
METRICS_FILENAME = "metrics.json"
PLOT_FILENAME = "walk_forward.png"


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


def _gradient_boosting_change(target: str) -> Any:
    return ChangeFromLast(_gradient_boosting(), target)


def _random_forest_change(target: str) -> Any:
    return ChangeFromLast(_random_forest(), target)


CHANGE_SUFFIX = "_change"
# Models of the change from the last value help today and the next two days. Further
# ahead they lost to models of the level in the walk-forward test, and every extra
# candidate adds training time, so they are only tried where they can win.
CHANGE_HORIZONS = (1, 2, 3)


def _gradient_boosting_blend(target: str) -> Any:
    return BlendWithWeekMean(_gradient_boosting(), target)


def _random_forest_blend(target: str) -> Any:
    return BlendWithWeekMean(_random_forest(), target)


BLEND_SUFFIX = "_blend"
# Half the model and half the weekly mean, three to six days ahead, where the
# weekly mean is the rule to beat. PM2.5 and PM10 only: they have that mean as a feature.
BLEND_HORIZONS = (4, 5, 6, 7)
BLEND_TARGETS = ("pm25", "pm10")
CANDIDATES = {
    "gradient_boosting": _gradient_boosting,
    "random_forest": _random_forest,
    "gradient_boosting_change": _gradient_boosting_change,
    "random_forest_change": _random_forest_change,
    "gradient_boosting_blend": _gradient_boosting_blend,
    "random_forest_blend": _random_forest_blend,
}


def candidates_for(horizon: int, target: str = "pm25") -> list[str]:
    """The candidate names tried for a slot."""
    names = []
    for name in CANDIDATES:
        if name.endswith(CHANGE_SUFFIX) and horizon not in CHANGE_HORIZONS:
            continue
        if name.endswith(BLEND_SUFFIX) and (horizon not in BLEND_HORIZONS or target not in BLEND_TARGETS):
            continue
        names.append(name)
    return names


def make_candidate(name: str, target: str) -> Any:
    """A new unfitted model; models of the change and blends need to know their target."""
    factory = CANDIDATES[name]
    return factory(target) if name.endswith((CHANGE_SUFFIX, BLEND_SUFFIX)) else factory()


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
    names = candidates_for(horizon, target)
    predictions = {}
    for name in names:
        base = name.removesuffix(BLEND_SUFFIX)
        if name != base and base in predictions:
            # A blend refits nothing: the same walk-forward forecasts, averaged with the weekly mean.
            predictions[name] = pd.Series(
                blend_with_week_mean(predictions[base], features, target), index=features.index
            ).where(predictions[base].notna())
        else:
            predictions[name] = walk_forward_predict(features, labels, partial(make_candidate, name, target), horizon)
    frame = pd.DataFrame({"actual": labels, **predictions, **baselines}).dropna()
    if frame.empty:
        raise ValueError(f"{slot}: no rows to evaluate")

    methods = [*names, *baselines]
    overall = {name: metrics(frame["actual"], frame[name]) for name in methods}
    latest = frame[frame.index > frame.index.max() - pd.Timedelta(days=LATEST_WINDOW_DAYS)]
    # The best candidate over all folds goes first. When it fails the gate, the
    # next one is tried: a candidate that beats every rule (and the published
    # model) on both windows has earned its place, even if another candidate has
    # the lower error over all folds. Only when none passes is the previous model
    # kept or a rule published, with the first candidate's reason.
    ranked = sorted(names, key=lambda name: overall[name]["mae"])
    candidate = ranked[0]
    first: dict[str, Any] | None = None
    for name in ranked:
        entry, promote = _decide(slot, name, latest, list(baselines), previous, features, models_dir, horizon, names)
        if promote:
            # A short recent window can favour a model by luck, so the full history must agree.
            overall_ok, overall_reason = promotion_gate(
                overall[name]["mae"], {base: overall[base]["mae"] for base in baselines}
            )
            if not overall_ok:
                promote = False
                entry = _fallback(previous, overall, list(baselines), f"over all folds it {overall_reason}")
        if promote:
            candidate = name
            break
        first = first or entry
        if entry["reason"].startswith(WAITING_REASON):
            # The published model cannot be judged yet, so no candidate can replace it.
            break
    if not promote:
        entry = first
    if promote:
        known = labels.notna().to_numpy()
        final_model = make_candidate(candidate, target)
        final_model.fit(features[known], labels[known])
        train_end = (features.index[known].max() + pd.Timedelta(days=horizon)).date().isoformat()
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(final_model, model_path(models_dir, slot))
        entry.update(
            {
                "method": candidate,
                "train_end": train_end,
                "promoted_at": now,
                "features": list(features.columns),
            }
        )
        if candidate != ranked[0]:
            entry["reason"] += f" ({ranked[0]} had the lower MAE over all folds but failed the gate)"

    entry["candidates"] = names
    for stale in ("residual_q80_by_level", "exceedance"):
        entry.pop(stale, None)
    range_fields, range_report = range_entry(frame["actual"], frame[entry["method"]], horizon, target)
    entry.update(range_fields)
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
        "range": range_report,
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
    names: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Apply the promotion gate on the latest walk-forward window."""
    window = latest
    previous_mae = None
    has_previous_model = bool(previous) and previous["method"] in CANDIDATES

    other_features = previous.get("features") != list(features.columns) if has_previous_model else False
    other_candidates = has_previous_model and names is not None and previous.get("candidates") != names
    stale_previous = other_features or other_candidates
    if stale_previous:
        # The candidate sees inputs the previous model never had (a feature was
        # added or removed), or was chosen among methods the previous model never
        # competed with. Waiting for unseen days would keep the older model for
        # weeks, so the candidate is judged like a first model: against every
        # baseline here and over all folds.
        has_previous_model = False
    if has_previous_model:
        # The previous model trained on data up to train_end. Only later rows are a fair test.
        cutoff = pd.Timestamp(previous["train_end"])
        window = latest[latest.index + pd.Timedelta(days=horizon) > cutoff]
        if len(window) < MIN_UNSEEN_DAYS:
            kept = dict(previous)
            kept["reason"] = f"{WAITING_REASON} {len(window)} days are unseen by the current model"
            return kept, False
        current_model = joblib.load(model_path(models_dir, slot))
        predicted = current_model.predict(model_inputs(features.loc[window.index], previous))
        previous_mae = float(np.abs(window["actual"].to_numpy() - predicted).mean())

    candidate_mae = float((window["actual"] - window[candidate]).abs().mean())
    baseline_maes = {
        name: float((window["actual"] - window[name]).abs().mean()) for name in baseline_names
    }
    promote, reason = promotion_gate(candidate_mae, baseline_maes, previous_mae)
    if promote:
        replaced = ""
        if other_features:
            replaced = " (replaces a model trained on other features)"
        elif other_candidates:
            replaced = " (replaces a model chosen among other methods)"
        return {"reason": f"promoted: {reason}{replaced}"}, True
    if has_previous_model or stale_previous:
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
    published_out: dict[str, pd.Series] | None = None,
) -> dict[str, Any]:
    """Evaluate every slot, update the registry and write metrics.json and a plot.

    `published_out`, when given, receives each slot's out-of-sample predictions
    from the method that is published, for models that build on the city forecast.
    """
    models_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(models_dir)
    targets = with_weather_targets(targets, exogenous)
    report: dict[str, Any] = {
        "generated_at": now,
        "as_of": as_of.date().isoformat(),
        "data": {
            target: {
                "first_day": targets[target].first_valid_index().date().isoformat(),
                "last_day": targets[target].last_valid_index().date().isoformat(),
                "valid_days": int(targets[target].notna().sum()),
            }
            for target in ALL_TARGETS
        },
        "daily": {},
        "monthly": {},
    }

    plot_frame = None
    plot_method = None
    for target in ALL_TARGETS:
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
            if published_out is not None:
                published_out[slot] = frame[entry["method"]]
            report["daily"][slot] = slot_report
            if slot == "pm25_h2":
                # Plot the best model against persistence even when persistence is published.
                plot_frame, plot_method = frame, slot_report["best_candidate"]

    monthly = monthly_targets(targets)
    for target in ALL_TARGETS:
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
