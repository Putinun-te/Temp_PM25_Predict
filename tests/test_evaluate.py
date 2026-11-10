import numpy as np
import pandas as pd
import pytest

from pm25.evaluate import (
    metrics,
    monthly_walk_forward,
    promotion_gate,
    residual_q80,
    season_errors,
    skill,
    walk_forward_predict,
)


def daily_frame(days=800):
    index = pd.date_range("2022-01-01", periods=days, freq="D")
    rng = np.random.default_rng(0)
    return pd.DataFrame({"x": rng.normal(size=days)}, index=index), pd.Series(
        rng.normal(20, 5, days), index=index
    )


class RecordingModel:
    log = []

    def fit(self, features, labels):
        self.train_index = features.index
        return self

    def predict(self, features):
        RecordingModel.log.append((self.train_index, features.index))
        return np.zeros(len(features))


@pytest.mark.parametrize("horizon", [1, 2])
def test_training_never_uses_labels_from_the_test_period_or_later(horizon):
    RecordingModel.log = []
    features, labels = daily_frame()
    walk_forward_predict(features, labels, RecordingModel, horizon)
    assert RecordingModel.log
    for train_index, test_index in RecordingModel.log:
        assert train_index.max() + pd.Timedelta(days=horizon) < test_index.min()


def test_training_window_expands_and_blocks_move_forward():
    RecordingModel.log = []
    features, labels = daily_frame()
    walk_forward_predict(features, labels, RecordingModel, 1)
    sizes = [len(train) for train, _ in RecordingModel.log]
    starts = [test.min() for _, test in RecordingModel.log]
    assert sizes == sorted(sizes)
    assert starts == sorted(starts)


def test_no_prediction_before_the_first_test_block():
    RecordingModel.log = []
    features, labels = daily_frame()
    predictions = walk_forward_predict(features, labels, RecordingModel, 1)
    assert predictions.first_valid_index() >= features.index.min() + pd.Timedelta(days=365)


def test_rows_with_unknown_labels_are_neither_trained_on_nor_scored():
    RecordingModel.log = []
    features, labels = daily_frame()
    labels.iloc[500:510] = np.nan
    predictions = walk_forward_predict(features, labels, RecordingModel, 1)
    assert predictions.iloc[500:510].isna().all()
    missing = labels.index[500:510]
    for train_index, _ in RecordingModel.log:
        assert not train_index.isin(missing).any()


def test_metrics_values():
    result = metrics(pd.Series([1.0, 3.0]), pd.Series([2.0, 2.0]))
    assert result["mae"] == 1.0
    assert result["rmse"] == 1.0
    assert result["r2"] == 0.0
    assert result["n"] == 2


def test_skill_is_positive_when_model_is_better():
    assert skill(5.0, 10.0) == 0.5
    assert skill(12.0, 10.0) < 0


def test_residual_q80():
    assert residual_q80(pd.Series([0.0] * 10), pd.Series(np.arange(1.0, 11.0))) == pytest.approx(8.2)


def test_season_errors_use_the_target_month():
    index = pd.date_range("2024-02-29", periods=1, freq="D")
    frame = pd.DataFrame({"actual": [10.0], "m": [8.0]}, index=index)
    assert set(season_errors(frame, ["m"], 1)) == {"hot_mar_may"}


def test_gate_promotes_a_candidate_better_than_everything():
    assert promotion_gate(4.0, {"persistence": 5.0, "seasonal7": 6.0}, 4.5)[0]


def test_gate_rejects_when_a_baseline_wins():
    promoted, reason = promotion_gate(5.5, {"persistence": 5.0, "seasonal7": 6.0})
    assert not promoted
    assert "persistence" in reason


def test_gate_rejects_when_the_previous_model_wins():
    promoted, reason = promotion_gate(4.0, {"persistence": 5.0}, 3.0)
    assert not promoted
    assert "previous" in reason


def test_gate_rejects_a_tie():
    assert not promotion_gate(5.0, {"persistence": 5.0})[0]


def test_gate_rejects_a_noise_level_improvement():
    assert not promotion_gate(4.99, {"persistence": 5.0})[0]
    assert promotion_gate(4.9, {"persistence": 5.0})[0]


def test_gate_without_previous_model_only_needs_baselines():
    assert promotion_gate(4.0, {"persistence": 5.0}, None)[0]


def test_monthly_walk_forward_ignores_the_future():
    index = pd.date_range("2021-01-01", periods=60, freq="MS")
    rng = np.random.default_rng(3)
    series = pd.Series(rng.uniform(10, 40, 60), index=index)
    original = monthly_walk_forward(series, 2)
    changed = series.copy()
    changed.iloc[40:] = 9999.0
    altered = monthly_walk_forward(changed, 2)
    months = original.index[original.index < index[40]]
    assert not months.empty
    pd.testing.assert_frame_equal(original.loc[months], altered.loc[months])


def test_monthly_walk_forward_requires_enough_history():
    index = pd.date_range("2021-01-01", periods=20, freq="MS")
    assert monthly_walk_forward(pd.Series(10.0, index=index), 2).empty
