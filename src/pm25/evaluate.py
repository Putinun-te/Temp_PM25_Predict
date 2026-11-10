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
