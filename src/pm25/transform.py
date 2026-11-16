"""Small scikit-learn transformers shared by the models."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


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
