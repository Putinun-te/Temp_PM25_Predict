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


def compare_ranges(actual: pd.Series, predicted: pd.Series, horizon: int) -> dict[str, object]:
    """Calibrate both range methods on older forecasts and score them on the newest year.

    Returns the coverage, mean width and interval score of each, and the method
    with the lower score. Both are then refitted on all forecasts for publishing.
    """
    paired = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if paired.empty:
        return {"chosen": "season"}
    split = paired.index.max() - pd.Timedelta(days=RANGE_HOLDOUT_DAYS)
    older, newer = paired[paired.index <= split], paired[paired.index > split]
    level = level_q80(older["actual"], older["predicted"])
    if level is None or newer.empty:
        return {"chosen": "season"}
    season_entry = {
        "residual_q80": residual_q80(older["actual"], older["predicted"]),
        "residual_q80_by_season": seasonal_q80(older["actual"], older["predicted"], horizon),
    }
    targets = newer.index + pd.Timedelta(days=horizon)
    widths = {
        "season": pd.Series([range_for(season_entry, day) for day in targets], index=newer.index, dtype=float),
        "level": newer["predicted"].map(lambda value: _level_width(level, value)),
    }
    result: dict[str, object] = {"holdout_days": int(len(newer))}
    for name, width in widths.items():
        low = (newer["predicted"] - width).clip(lower=0)
        high = newer["predicted"] + width
        inside = (newer["actual"] >= low) & (newer["actual"] <= high)
        result[name] = {
            "coverage": float(inside.mean()),
            "mean_width": float((high - low).mean()),
            "interval_score": interval_score(newer["actual"], low, high),
        }
    result["chosen"] = min(("season", "level"), key=lambda name: result[name]["interval_score"])  # type: ignore[index]
    return result


def range_entry(actual: pd.Series, predicted: pd.Series, horizon: int) -> tuple[dict[str, object], dict[str, object]]:
    """Return the registry fields for the published range and the comparison behind them."""
    comparison = compare_ranges(actual, predicted, horizon)
    fields: dict[str, object] = {
        "residual_q80": residual_q80(actual, predicted),
        "residual_q80_by_season": seasonal_q80(actual, predicted, horizon),
        "range_method": comparison["chosen"],
    }
    if comparison["chosen"] == "level":
        fields["residual_q80_by_level"] = level_q80(actual, predicted)
    return fields, comparison


def range_for(entry: Mapping[str, object], target_date: pd.Timestamp, value: float | None = None) -> float | None:
    """Return the range half-width for a forecast of `target_date` with value `value`.

    Slots whose newest year scored better with level bands use them; the rest,
    and entries trained before bands existed, use the season of the target date.
    """
    by_level = entry.get("residual_q80_by_level")
    if entry.get("range_method") == "level" and by_level and value is not None and not pd.isna(value):
        return _level_width(by_level, float(value))  # type: ignore[arg-type]
    by_season = entry.get("residual_q80_by_season") or {}
    return by_season.get(season_of(target_date.month), entry.get("residual_q80"))  # type: ignore[union-attr, return-value]


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
