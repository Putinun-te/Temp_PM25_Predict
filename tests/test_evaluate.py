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


def test_seasonal_ranges_follow_the_target_month_and_fall_back():
    from pm25.evaluate import range_for, seasonal_q80

    index = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    actual = pd.Series(10.0, index=index)
    # Errors of 8 in the haze months and 1 otherwise.
    haze = (index + pd.Timedelta(days=1)).month.isin([11, 12, 1, 2])
    predicted = actual - np.where(haze, 8.0, 1.0)

    by_season = seasonal_q80(actual, predicted, horizon=1)
    assert by_season["cool_haze_nov_feb"] == 8.0
    assert by_season["rainy_jun_oct"] == 1.0

    entry = {"residual_q80": 3.0, "residual_q80_by_season": {"cool_haze_nov_feb": 8.0}}
    assert range_for(entry, pd.Timestamp("2026-01-15")) == 8.0
    assert range_for(entry, pd.Timestamp("2026-07-15")) == 3.0  # Season missing
    assert range_for({"residual_q80": 3.0}, pd.Timestamp("2026-01-15")) == 3.0  # Older registry entry


def _heteroscedastic(days=900, seed=0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-01", periods=days, freq="D")
    predicted = pd.Series(rng.uniform(10, 80, days), index=index)
    # The error grows with the forecast level, as PM2.5 errors do.
    actual = predicted + rng.normal(0, 1, days) * predicted * 0.25
    return actual, predicted


def test_level_bands_widen_with_the_forecast():
    from pm25.evaluate import level_q80, range_for

    actual, predicted = _heteroscedastic()
    spec = level_q80(actual, predicted)
    assert len(spec["q80"]) == 4 and spec["q80"] == sorted(spec["q80"])
    entry = {"range_method": "level", "residual_q80_by_level": spec, "residual_q80": 9.0}
    day = pd.Timestamp("2026-07-01")
    assert range_for(entry, day, 15.0) < range_for(entry, day, 70.0)
    # Without a value, or for an entry that chose seasons, the seasonal range applies.
    assert range_for(entry, day) == 9.0
    assert range_for({**entry, "range_method": "season"}, day, 70.0) == 9.0


def test_level_ranges_win_when_errors_grow_with_level():
    from pm25.evaluate import compare_ranges, range_entry

    actual, predicted = _heteroscedastic()
    comparison = compare_ranges(actual, predicted, horizon=1)
    assert comparison["chosen"] == "level"
    assert comparison["level"]["interval_score"] < comparison["season"]["interval_score"]
    assert 0.7 < comparison["level"]["coverage"] < 0.9
    fields, _ = range_entry(actual, predicted, 1)
    assert fields["range_method"] == "level" and fields["residual_q80_by_level"]["edges"]


def test_short_history_keeps_seasonal_ranges():
    from pm25.evaluate import compare_ranges

    actual, predicted = _heteroscedastic(days=200)
    assert compare_ranges(actual, predicted, horizon=1)["chosen"] == "season"


def test_a_recent_window_wins_when_errors_have_grown():
    from pm25.evaluate import compare_ranges, range_entry

    rng = np.random.default_rng(1)
    index = pd.date_range("2022-01-01", periods=1500, freq="D")
    predicted = pd.Series(70.0 + rng.normal(0, 5, len(index)), index=index)
    # Errors double in the last 600 days, as humidity errors grew: old calibration is too narrow.
    scale = np.where(np.arange(len(index)) >= 900, 8.0, 4.0)
    actual = predicted + rng.normal(0, 1, len(index)) * scale
    comparison = compare_ranges(actual, predicted, horizon=1)
    assert comparison["season"]["coverage"] < 0.73
    assert comparison["chosen"] in {"season_365", "level_365"}
    fields, _ = range_entry(actual, predicted, 1, "rh_pct")
    assert fields["range_method"] == comparison["chosen"] and "exceedance" not in fields


def test_chance_above_the_standard_follows_past_errors():
    from pm25.evaluate import chance_above, compare_exceedance, entry_chance_above, exceedance_quantiles, range_entry

    actual, predicted = _heteroscedastic(days=1200)
    spec = exceedance_quantiles(actual, predicted)
    assert chance_above(spec, 15.0, 37.5) == 0.0
    assert 0.3 < chance_above(spec, 37.5, 37.5) < 0.7
    assert chance_above(spec, 75.0, 37.5) == 1.0
    check = compare_exceedance(actual, predicted, 37.5)
    assert check["published"] and check["brier"] < check["climatology_brier"]
    fields, report = range_entry(actual, predicted, 1, "pm25")
    assert fields["exceedance"]["threshold"] == 37.5 and report["exceedance"]["published"]
    assert entry_chance_above(fields, 75.0) == 1.0
    assert entry_chance_above({}, 75.0) is None


def test_no_chance_is_published_when_the_newest_year_never_went_above():
    from pm25.evaluate import compare_exceedance

    actual, predicted = _heteroscedastic(days=1200)
    check = compare_exceedance(actual, predicted, 500.0)
    assert check["events"] == 0 and not check["published"]


def test_chances_are_published_for_each_band_edge_that_passes():
    from pm25.evaluate import entry_chance_above, entry_chances_above, range_entry

    actual, predicted = _heteroscedastic(days=1200)
    fields, report = range_entry(actual, predicted, 1, "pm25")
    checks = report["exceedance_by_threshold"]
    assert set(checks) == {"25", "37.5", "75"}
    published = [t for t in (25.0, 37.5, 75.0) if checks[f"{t:g}"]["published"]]
    assert fields["exceedance"]["thresholds"] == published and 37.5 in published
    chances = entry_chances_above(fields, 30.0)
    assert [c["threshold"] for c in chances] == published
    # A higher edge is never more likely than a lower one.
    assert all(a["p"] >= b["p"] for a, b in zip(chances, chances[1:]))
    # Entries from before several edges keep working.
    old = {"exceedance": {k: v for k, v in fields["exceedance"].items() if k != "thresholds"}}
    assert entry_chances_above(old, 30.0) == [{"threshold": 37.5, "p": entry_chance_above(old, 30.0)}]


def test_standard_chance_is_absent_when_only_a_lower_edge_passes():
    from pm25.evaluate import entry_chance_above, entry_chances_above

    entry = {"exceedance": {"thresholds": [80.0], "edges": [], "quantiles": [[-5.0, 0.0, 5.0]]}}
    assert entry_chance_above(entry, 78.0) is None
    assert entry_chances_above(entry, 78.0) == [{"threshold": 80.0, "p": 0.33}]


def test_range_choice_is_also_scored_as_if_made_a_year_earlier():
    from pm25.evaluate import compare_ranges

    actual, predicted = _heteroscedastic(days=1200)
    comparison = compare_ranges(actual, predicted, 1)
    honest = comparison["honest"]
    # The method chosen without the newest year, scored on the newest year.
    assert honest["chosen_a_year_earlier"] in comparison
    assert honest["coverage"] == comparison[honest["chosen_a_year_earlier"]]["coverage"]
    # Too little history for a choice a year earlier: no honest score.
    short = compare_ranges(actual.iloc[-500:], predicted.iloc[-500:], 1)
    assert "honest" not in short
