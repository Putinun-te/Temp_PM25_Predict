"""Honest evaluation: walk-forward splits, error metrics and the promotion gate."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd

from pm25.features import monthly_forecast

MIN_TRAIN_ROWS = 180
FIRST_TEST_AFTER_DAYS = 365
BLOCK_DAYS = 30
MIN_HISTORY_MONTHS = 24
MIN_RELATIVE_IMPROVEMENT = 0.01
SEASONS = {
    "cool_haze_nov_feb": (11, 12, 1, 2),
    "hot_mar_may": (3, 4, 5),
    "rainy_jun_oct": (6, 7, 8, 9, 10),
}


def metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float | int]:
    """Return MAE, RMSE, R2 and the row count."""
    error = actual - predicted
    total = ((actual - actual.mean()) ** 2).sum()
    return {
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "r2": float(1.0 - (error**2).sum() / total) if total > 0 else float("nan"),
        "n": int(len(actual)),
    }


def skill(model_mae: float, baseline_mae: float) -> float:
    """Return the fraction of baseline error removed. Above zero means better."""
    return 1.0 - model_mae / baseline_mae


def residual_q80(actual: pd.Series, predicted: pd.Series) -> float:
    """Return the size of error that 80 % of past forecasts stayed within."""
    return float(np.quantile((actual - predicted).abs(), 0.8))


MIN_SEASON_ROWS = 60


def season_of(month: int) -> str:
    return next(name for name, months in SEASONS.items() if month in months)


def seasonal_q80(actual: pd.Series, predicted: pd.Series, horizon: int) -> dict[str, float]:
    """Return the 80 % error size per season of the target date.

    Errors are several times larger in the haze season than in the rainy season,
    so one range for the whole year is too narrow in winter and too wide in
    summer. A season with too few rows is left out and falls back to the
    all-year value.
    """
    error = (actual - predicted).abs().dropna()
    months = (error.index + pd.Timedelta(days=horizon)).month
    result: dict[str, float] = {}
    for season, season_months in SEASONS.items():
        subset = error[months.isin(season_months)]
        if len(subset) >= MIN_SEASON_ROWS:
            result[season] = float(np.quantile(subset, 0.8))
    return result


LEVEL_BINS = 4
RANGE_HOLDOUT_DAYS = 365
RANGE_ALPHA = 0.2  # The range is meant to hold 80 % of outcomes
RANGE_TARGET_COVERAGE = 1 - RANGE_ALPHA
# A method whose newest-year coverage is this close to 80 % counts as honest;
# among those the sharpest (lowest interval score) is published.
RANGE_COVERAGE_TOLERANCE = 0.07
# Calibration windows: every past forecast, or only the newest two years or one
# year, for targets whose errors have drifted (humidity has).
RANGE_WINDOWS: tuple[int | None, ...] = (None, 730, 365)
# A "recent" range is the 80 % error of the newest days at each weekly retrain.
# It follows drift within the year (humidity's errors grow and shrink for weeks
# at a time), so it is tried for the weather targets, whose daily index has one
# row per day. Scored as it would have been published: refitted once a week,
# so a forecast uses errors up to its horizon plus seven days old.
RECENT_RANGE_DAYS = 90
RECENT_RANGE_MIN_ROWS = 45
RECENT_RANGE_REFIT_DAYS = 7
RECENT_RANGE_TARGETS = ("temp_c", "rh_pct")
# Thai 24-hour standards in µg/m³; the chance of going above them is published.
STANDARDS = {"pm25": 37.5, "pm10": 120.0}
# Edges of the Pollution Control Department colour bands, standard included. A
# chance is published for each edge that passes the same test as the standard:
# "moderate or worse", "starting to affect health or worse" and "affects health".
THRESHOLDS = {"pm25": (25.0, 37.5, 75.0), "pm10": (80.0, 120.0)}
EXCEEDANCE_QUANTILES = tuple(float(q) for q in np.linspace(0.01, 0.99, 50))
# A chance is only checked, and so only published, when the newest year went above the standard this often.
MIN_EXCEEDANCE_EVENTS = 10


def level_q80(actual: pd.Series, predicted: pd.Series, bins: int = LEVEL_BINS) -> dict[str, list[float]] | None:
    """Return the 80 % error size for each band of forecast level.

    A forecast of 60 µg/m³ misses by far more than one of 15, in any season, so
    the range widens with the forecast itself. The bands split past forecasts
    into equal counts; None when a band would have too few rows.
    """
    paired = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if len(paired) < bins * MIN_SEASON_ROWS:
        return None
    edges = np.unique(np.quantile(paired["predicted"], np.linspace(0, 1, bins + 1)[1:-1]))
    band = np.searchsorted(edges, paired["predicted"].to_numpy(), side="right")
    error = (paired["actual"] - paired["predicted"]).abs().to_numpy()
    q80 = [float(np.quantile(error[band == index], 0.8)) for index in range(len(edges) + 1)]
    return {"edges": [float(edge) for edge in edges], "q80": q80}


def _level_width(spec: Mapping[str, list[float]], value: float) -> float:
    return spec["q80"][int(np.searchsorted(spec["edges"], value, side="right"))]


def interval_score(actual: pd.Series, low: pd.Series, high: pd.Series, alpha: float = RANGE_ALPHA) -> float:
    """Mean width plus a penalty for each miss, scaled by how far outside it fell. Lower is better."""
    below = (low - actual).clip(lower=0)
    above = (actual - high).clip(lower=0)
    return float(((high - low) + (2 / alpha) * (below + above)).mean())


def _window(frame: pd.DataFrame, days: int | None) -> pd.DataFrame:
    if days is None or frame.empty:
        return frame
    return frame[frame.index > frame.index.max() - pd.Timedelta(days=days)]


def _method_name(kind: str, days: int | None) -> str:
    return kind if days is None else f"{kind}_{days}"


def _parse_method(name: str) -> tuple[str, int | None]:
    kind, _, days = name.partition("_")
    return kind, int(days) if days else None


def _fit_spec(kind: str, frame: pd.DataFrame, horizon: int | None) -> dict[str, object] | None:
    """Fit one kind of range on `frame`: flat, season (needs a horizon) or level."""
    if frame.empty:
        return None
    if kind == "recent":
        if len(frame) < RECENT_RANGE_MIN_ROWS:
            return None
        return {"residual_q80_recent": residual_q80(frame["actual"], frame["predicted"])}
    if kind == "level":
        spec = level_q80(frame["actual"], frame["predicted"])
        return None if spec is None else {"residual_q80_by_level": spec}
    flat = residual_q80(frame["actual"], frame["predicted"])
    if kind == "season" and horizon is not None:
        return {"residual_q80": flat, "residual_q80_by_season": seasonal_q80(frame["actual"], frame["predicted"], horizon)}
    return {"residual_q80": flat}


def _widths(kind: str, spec: Mapping[str, object], frame: pd.DataFrame, horizon: int | None) -> pd.Series:
    if kind == "level":
        return frame["predicted"].map(lambda value: _level_width(spec["residual_q80_by_level"], value))  # type: ignore[arg-type]
    if kind == "season" and horizon is not None:
        days = frame.index + pd.Timedelta(days=horizon)
        return pd.Series([range_for(spec, day) for day in days], index=frame.index, dtype=float)
    return pd.Series(spec["residual_q80"], index=frame.index, dtype=float)


def recent_widths(paired: pd.DataFrame, horizon: int | None, days: int = RECENT_RANGE_DAYS) -> pd.Series:
    """The recent range each origin of `paired` would have been published with.

    The error of origin o is known at o + horizon, and the range is refitted at
    most RECENT_RANGE_REFIT_DAYS before it is used, so origin t sees the errors
    of origins up to t - horizon - RECENT_RANGE_REFIT_DAYS.
    """
    error = (paired["actual"] - paired["predicted"]).abs().sort_index()
    error.index = error.index + pd.Timedelta(days=(horizon or 0) + RECENT_RANGE_REFIT_DAYS)
    width = error.rolling(f"{days}D", min_periods=RECENT_RANGE_MIN_ROWS).quantile(0.8)
    width = width[~width.index.duplicated(keep="last")]
    return width.reindex(width.index.union(paired.index)).ffill().reindex(paired.index)


def compare_ranges(
    actual: pd.Series,
    predicted: pd.Series,
    horizon: int | None,
    kinds: tuple[str, ...] = ("season", "level"),
    nested: bool = True,
) -> dict[str, object]:
    """Calibrate each range method on older forecasts and score it on the newest year.

    Every kind is tried with each calibration window. Methods whose coverage on
    the newest year is within the tolerance of 80 % are eligible, and the one
    with the lowest interval score among them is chosen; when none is eligible,
    the one with coverage closest to 80 %. The chosen method is then refitted on
    the same window ending at the newest forecast, for publishing.

    The chosen method's newest-year score is slightly optimistic, because the
    same year picked it. `honest` repeats the whole choice one year earlier,
    without the newest year, and gives that method's newest-year score: what
    the selection would have delivered had it been run a year ago.
    """
    paired = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    fallback = kinds[0]
    if paired.empty:
        return {"chosen": fallback}
    split = paired.index.max() - pd.Timedelta(days=RANGE_HOLDOUT_DAYS)
    older, newer = paired[paired.index <= split], paired[paired.index > split]
    if newer.empty or older.empty:
        return {"chosen": fallback}
    result: dict[str, object] = {"holdout_days": int(newer.index.nunique())}
    scores: dict[str, dict[str, float]] = {}
    for kind in kinds:
        for days in (RECENT_RANGE_DAYS,) if kind == "recent" else RANGE_WINDOWS:
            if kind == "recent":
                width = recent_widths(paired, horizon, days).reindex(newer.index)
                if width.isna().any():
                    continue
            else:
                spec = _fit_spec(kind, _window(older, days), horizon)
                if spec is None:
                    continue
                width = _widths(kind, spec, newer, horizon)
            low = (newer["predicted"] - width).clip(lower=0)
            high = newer["predicted"] + width
            inside = (newer["actual"] >= low) & (newer["actual"] <= high)
            scores[_method_name(kind, days)] = {
                "coverage": float(inside.mean()),
                "mean_width": float((high - low).mean()),
                "interval_score": interval_score(newer["actual"], low, high),
            }
    if not scores:
        return {"chosen": fallback}
    result.update(scores)
    eligible = [name for name, score in scores.items() if abs(score["coverage"] - RANGE_TARGET_COVERAGE) <= RANGE_COVERAGE_TOLERANCE]
    if eligible:
        result["chosen"] = min(eligible, key=lambda name: scores[name]["interval_score"])
    else:
        result["chosen"] = min(scores, key=lambda name: abs(scores[name]["coverage"] - RANGE_TARGET_COVERAGE))
    if nested:
        earlier = compare_ranges(older["actual"], older["predicted"], horizon, kinds, nested=False)
        before = earlier.get("chosen")
        if "holdout_days" in earlier and before in scores:
            result["honest"] = {"chosen_a_year_earlier": before, **scores[before]}
    return result


def exceedance_quantiles(actual: pd.Series, predicted: pd.Series) -> dict[str, object] | None:
    """Signed error quantiles per band of forecast level, for the chance of going above a standard."""
    paired = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if len(paired) < LEVEL_BINS * MIN_SEASON_ROWS:
        return None
    edges = np.unique(np.quantile(paired["predicted"], np.linspace(0, 1, LEVEL_BINS + 1)[1:-1]))
    band = np.searchsorted(edges, paired["predicted"].to_numpy(), side="right")
    error = (paired["actual"] - paired["predicted"]).to_numpy()
    return {
        "edges": [float(edge) for edge in edges],
        "quantiles": [[round(float(v), 3) for v in np.quantile(error[band == i], EXCEEDANCE_QUANTILES)] for i in range(len(edges) + 1)],
    }


def chance_above(spec: Mapping[str, object] | None, value: float | None, threshold: float) -> float | None:
    """Chance that the outcome is above `threshold` given the forecast `value`, from past errors."""
    if spec is None or value is None or pd.isna(value):
        return None
    quantiles = np.asarray(spec["quantiles"][int(np.searchsorted(spec["edges"], value, side="right"))])  # type: ignore[index]
    return float(np.mean(value + quantiles > threshold))


def compare_exceedance(actual: pd.Series, predicted: pd.Series, threshold: float) -> dict[str, object]:
    """Score the chance of going above `threshold` on the newest year, calibrated on older forecasts.

    It is published only when the newest year went above the threshold at
    least MIN_EXCEEDANCE_EVENTS times and its Brier score beats always saying
    the historical rate, the climatological chance.
    """
    paired = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    split = paired.index.max() - pd.Timedelta(days=RANGE_HOLDOUT_DAYS) if not paired.empty else None
    older = paired[paired.index <= split] if split is not None else paired
    newer = paired[paired.index > split] if split is not None else paired
    spec = exceedance_quantiles(older["actual"], older["predicted"]) if not older.empty else None
    if spec is None or newer.empty:
        return {"threshold": threshold, "published": False, "reason": "not enough history"}
    chances = np.array([chance_above(spec, value, threshold) for value in newer["predicted"]])
    outcome = (newer["actual"] > threshold).to_numpy(dtype=float)
    base_rate = float((older["actual"] > threshold).mean())
    brier = float(np.mean((chances - outcome) ** 2))
    climatology = float(np.mean((base_rate - outcome) ** 2))
    return {
        "threshold": threshold,
        "holdout_days": int(newer.index.nunique()),
        "events": int(outcome.sum()),
        "brier": brier,
        "climatology_brier": climatology,
        "published": bool(outcome.sum() >= MIN_EXCEEDANCE_EVENTS and brier < climatology),
    }


def fitted_range(
    actual: pd.Series, predicted: pd.Series, horizon: int | None, kinds: tuple[str, ...] = ("season", "level")
) -> tuple[dict[str, object], dict[str, object]]:
    """Choose a range method and fit it on its window ending at the newest forecast."""
    comparison = compare_ranges(actual, predicted, horizon, kinds)
    kind, days = _parse_method(str(comparison["chosen"]))
    paired = _window(pd.DataFrame({"actual": actual, "predicted": predicted}).dropna(), days)
    fields: dict[str, object] = {"range_method": comparison["chosen"]}
    fields.update(_fit_spec(kind, paired, horizon) or {})
    return fields, comparison


def width_for(spec: Mapping[str, object], value: float | None) -> float | None:
    """Half-width from a fitted range without seasons: level bands when chosen, else the flat value."""
    by_level = spec.get("residual_q80_by_level")
    if str(spec.get("range_method", "")).startswith("level") and by_level and value is not None and not pd.isna(value):
        return _level_width(by_level, float(value))  # type: ignore[arg-type]
    return spec.get("residual_q80")  # type: ignore[return-value]


def range_entry(
    actual: pd.Series, predicted: pd.Series, horizon: int, target: str | None = None
) -> tuple[dict[str, object], dict[str, object]]:
    """Return the registry fields for the published range and the comparison behind them."""
    kinds = ("season", "level", "recent") if target in RECENT_RANGE_TARGETS else ("season", "level")
    fitted, comparison = fitted_range(actual, predicted, horizon, kinds)
    fields: dict[str, object] = {
        # The all-year and seasonal values stay as the fallback for any forecast without a value.
        "residual_q80": residual_q80(actual, predicted),
        "residual_q80_by_season": seasonal_q80(actual, predicted, horizon),
        **fitted,
    }
    if target in THRESHOLDS:
        spec, checks = exceedance_entry(actual, predicted, target)
        comparison["exceedance"] = checks[threshold_key(STANDARDS[target])]
        comparison["exceedance_by_threshold"] = checks
        if spec is not None:
            fields["exceedance"] = spec
    return fields, comparison


def exceedance_entry(
    actual: pd.Series, predicted: pd.Series, target: str
) -> tuple[dict[str, object] | None, dict[str, dict[str, object]]]:
    """Test the chance above each band edge of `target`; return the spec of those that passed, and every test."""
    checks = {threshold_key(t): compare_exceedance(actual, predicted, t) for t in THRESHOLDS[target]}
    published = [t for t in THRESHOLDS[target] if checks[threshold_key(t)]["published"]]
    quantiles = exceedance_quantiles(actual, predicted) if published else None
    if not quantiles:
        return None, checks
    spec: dict[str, object] = {"thresholds": published, **quantiles}
    if STANDARDS[target] in published:
        spec["threshold"] = STANDARDS[target]
    return spec, checks


def threshold_key(threshold: float) -> str:
    """37.5 reads "37.5" and 80.0 reads "80", the keys of the training report."""
    return f"{threshold:g}"


def range_for(entry: Mapping[str, object], target_date: pd.Timestamp, value: float | None = None) -> float | None:
    """Return the range half-width for a forecast of `target_date` with value `value`.

    Slots whose newest year scored better with level bands use them; the rest,
    and entries trained before bands existed, use the season of the target date.
    """
    if str(entry.get("range_method", "")).startswith("recent") and entry.get("residual_q80_recent") is not None:
        return entry["residual_q80_recent"]  # type: ignore[return-value]
    by_level = entry.get("residual_q80_by_level")
    if str(entry.get("range_method", "")).startswith("level") and by_level and value is not None and not pd.isna(value):
        return _level_width(by_level, float(value))  # type: ignore[arg-type]
    by_season = entry.get("residual_q80_by_season") or {}
    return by_season.get(season_of(target_date.month), entry.get("residual_q80"))  # type: ignore[union-attr, return-value]


def entry_chance_above(entry: Mapping[str, object], value: float | None) -> float | None:
    """The published chance of going above the standard, or None when the slot has none."""
    spec = entry.get("exceedance")
    if not spec or spec.get("threshold") is None:  # type: ignore[union-attr]
        return None
    chance = chance_above(spec, value, float(spec["threshold"]))  # type: ignore[index, arg-type]
    return None if chance is None else round(chance, 2)


def entry_chances_above(entry: Mapping[str, object], value: float | None) -> list[dict[str, float]] | None:
    """The published chance above each tested band edge, lowest edge first, or None.

    A list rather than a mapping, because Firebase keys cannot hold "37.5".
    """
    spec = entry.get("exceedance")
    if not spec or value is None or pd.isna(value):
        return None
    # Entries trained before several edges existed hold only the standard.
    thresholds = spec.get("thresholds") or [spec["threshold"]]  # type: ignore[union-attr, index]
    result = []
    for threshold in sorted(float(t) for t in thresholds):  # type: ignore[union-attr]
        chance = chance_above(spec, value, threshold)
        if chance is not None:
            result.append({"threshold": threshold, "p": round(chance, 2)})
    return result or None


def walk_forward_predict(
    features: pd.DataFrame,
    labels: pd.Series,
    make_model: Callable[[], object],
    horizon: int,
    first_test_after_days: int = FIRST_TEST_AFTER_DAYS,
    block_days: int = BLOCK_DAYS,
) -> pd.Series:
    """Return out-of-sample predictions from an expanding training window.

    A block is predicted only by a model trained on rows whose label date falls
    before the block starts, so no training row uses an outcome from the future.
    The data order is never shuffled.
    """
    predictions = pd.Series(np.nan, index=features.index, dtype=float)
    known = labels.notna().to_numpy()
    first_block = features.index.min() + pd.Timedelta(days=first_test_after_days)
    label_dates = features.index + pd.Timedelta(days=horizon)

    for block_start in pd.date_range(first_block, features.index.max(), freq=f"{block_days}D"):
        block_end = block_start + pd.Timedelta(days=block_days - 1)
        in_block = (features.index >= block_start) & (features.index <= block_end) & known
        in_training = (label_dates < block_start) & known
        if in_training.sum() < MIN_TRAIN_ROWS or not in_block.any():
            continue
        model = make_model()
        model.fit(features[in_training], labels[in_training])
        predictions[in_block] = model.predict(features[in_block])
    return predictions


def season_errors(
    frame: pd.DataFrame, columns: list[str], horizon: int
) -> dict[str, dict[str, float | int]]:
    """Return MAE per method for each Bangkok season of the target date."""
    months = (frame.index + pd.Timedelta(days=horizon)).month
    report: dict[str, dict[str, float | int]] = {}
    for season, season_months in SEASONS.items():
        subset = frame[months.isin(season_months)]
        if subset.empty:
            continue
        entry: dict[str, float | int] = {"n": int(len(subset))}
        entry.update(
            {column: float((subset["actual"] - subset[column]).abs().mean()) for column in columns}
        )
        report[season] = entry
    return report


def promotion_gate(
    candidate_mae: float,
    baseline_maes: Mapping[str, float],
    previous_mae: float | None = None,
    min_improvement: float = MIN_RELATIVE_IMPROVEMENT,
) -> tuple[bool, str]:
    """Decide whether a candidate replaces the current method.

    It must reduce MAE by at least `min_improvement` against every baseline and,
    when a previous model exists, against that model on the same rows. The
    margin stops noise-level differences from flipping the published method.
    """

    def beats(other: float) -> bool:
        return candidate_mae < other * (1.0 - min_improvement)

    for name, value in baseline_maes.items():
        if not beats(value):
            return False, f"does not beat baseline {name}"
    if previous_mae is None:
        return True, "beats every baseline"
    if not beats(previous_mae):
        return False, "does not beat the previous model"
    return True, "beats every baseline and the previous model"


def monthly_walk_forward(
    series: pd.Series, horizon: int, min_history_months: int = MIN_HISTORY_MONTHS
) -> pd.DataFrame:
    """Return out-of-sample monthly forecasts, each using only months up to its origin."""
    rows = []
    for month, actual in series.dropna().items():
        origin = month - pd.DateOffset(months=horizon)
        history = series[series.index <= origin]
        if history.notna().sum() < min_history_months:
            continue
        forecast = monthly_forecast(history, month, horizon)
        rows.append(
            {
                "month": month,
                "actual": actual,
                **forecast,
                "last_year": series.get(month - pd.DateOffset(years=1), np.nan),
            }
        )
    columns = ["actual", "climatology", "anomaly", "last_year"]
    if not rows:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="month"))
    return pd.DataFrame(rows).set_index("month")
