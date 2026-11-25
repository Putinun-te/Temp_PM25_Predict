"""Small scikit-learn transformers shared by the models."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin, clone


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


class ChangeFromLast(BaseEstimator, RegressorMixin):
    """Fit a model to the change from the last known value, then add that value back.

    A model of the level is pulled towards what usually happens on that day of
    the year. In a season that runs cleaner or dirtier than usual, its forecast
    for the next days stays near the usual level. A model of the change starts
    from where the series is now.

    The starting value is the target's value on the origin day, or its recent
    mean when that day is missing. `starts` names other columns to start from,
    tried in order (the hourly model starts from the newest measured hour). Rows
    with no starting value are left out of training and get no forecast.
    """

    def __init__(self, estimator: Any, target: str, starts: tuple[str, ...] | None = None):
        self.estimator = estimator
        self.target = target
        self.starts = starts

    def _start(self, features: pd.DataFrame) -> pd.Series:
        # Models saved before `starts` existed have no such attribute.
        names = getattr(self, "starts", None) or (
            f"{self.target}_lag0", f"{self.target}_mean3", f"{self.target}_mean7"
        )
        start = features[names[0]]
        for name in names[1:]:
            if name in features:
                start = start.fillna(features[name])
        return start

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> "ChangeFromLast":
        start = self._start(features)
        known = start.notna().to_numpy()
        change = np.asarray(labels, dtype=float) - start.to_numpy()  # positions, since hourly rows repeat a day
        self.model_ = clone(self.estimator).fit(features[known], change[known])
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return self.model_.predict(features) + self._start(features).to_numpy()


class BlendWithWeekMean(BaseEstimator, RegressorMixin):
    """Average a model's forecast with the mean of the last seven days.

    Three to six days ahead, the weekly mean is a hard rule to beat in calm
    weeks while the model catches the turns. Half of each was better than either
    over the newest 90 days and close to the model over all folds. When the
    weekly mean is missing, the model's forecast is used alone.
    """

    def __init__(self, estimator: Any, target: str):
        self.estimator = estimator
        self.target = target

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> "BlendWithWeekMean":
        self.model_ = clone(self.estimator).fit(features, labels)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return blend_with_week_mean(self.model_.predict(features), features, self.target)


def blend_with_week_mean(predicted: Any, features: pd.DataFrame, target: str) -> np.ndarray:
    """Half the forecast and half the weekly mean, or the forecast alone where that mean is missing."""
    predicted = np.asarray(predicted, dtype=float)
    week = features[f"{target}_mean7"].to_numpy(dtype=float)
    return np.where(np.isnan(week), predicted, (predicted + week) / 2)
