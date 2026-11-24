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
    mean when that day is missing. Rows with neither are left out of training
    and get no forecast.
    """

    def __init__(self, estimator: Any, target: str):
        self.estimator = estimator
        self.target = target

    def _start(self, features: pd.DataFrame) -> pd.Series:
        start = features[f"{self.target}_lag0"]
        for name in (f"{self.target}_mean3", f"{self.target}_mean7"):
            if name in features:
                start = start.fillna(features[name])
        return start

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> "ChangeFromLast":
        start = self._start(features)
        known = start.notna().to_numpy()
        self.model_ = clone(self.estimator).fit(features[known], (labels - start)[known])
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return self.model_.predict(features) + self._start(features).to_numpy()
