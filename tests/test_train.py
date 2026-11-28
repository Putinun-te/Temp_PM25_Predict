import json

import joblib
import numpy as np
import pandas as pd
import pytest

import pm25.train as train_module
from pm25.train import model_path, train_monthly, train_slot


class PerfectModel:
    """Reads the true answer from a test-only feature."""

    def fit(self, features, labels):
        return self

    def predict(self, features):
        return features["answer"].to_numpy()


class OffByTenModel(PerfectModel):
    def predict(self, features):
        return features["answer"].to_numpy() + 10.0


class OffByFiveModel(PerfectModel):
    def predict(self, features):
        return features["answer"].to_numpy() + 5.0


DAYS = 700
INDEX = pd.date_range("2022-01-01", periods=DAYS, freq="D", name="date")
NOW = "2024-01-01T00:00:00+07:00"


def inputs():
    rng = np.random.default_rng(5)
    labels = pd.Series(rng.uniform(10, 60, DAYS), index=INDEX)
    features = pd.DataFrame({"answer": labels.fillna(0.0)}, index=INDEX)
    baselines = {
        "persistence": labels + 3.0,
        "seasonal7": labels - 4.0,
    }
    return features, labels, baselines


def use(monkeypatch, model):
    monkeypatch.setattr(train_module, "CANDIDATES", {"candidate": model})


def run(tmp_path, previous=None):
    features, labels, baselines = inputs()
    return train_slot("pm25", 1, features, labels, baselines, previous, tmp_path, NOW)


def test_good_candidate_is_promoted_and_saved(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    entry, report, _ = run(tmp_path)
    assert entry["method"] == "candidate"
    assert report["published_method"] == "candidate"
    assert model_path(tmp_path, "pm25_h1").exists()


def test_candidate_worse_than_baselines_publishes_the_best_baseline(monkeypatch, tmp_path):
    use(monkeypatch, OffByTenModel)
    entry, _, _ = run(tmp_path)
    assert entry["method"] == "persistence"
    assert "baseline used" in entry["reason"]
    assert not model_path(tmp_path, "pm25_h1").exists()


def test_recent_luck_is_not_enough_to_promote(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    features, labels, baselines = inputs()
    # The candidate is perfect only in the most recent 90 days and poor before that.
    features["answer"] = labels.where(INDEX >= INDEX[-90], labels + 20.0)
    entry, _, _ = train_slot("pm25", 1, features, labels, baselines, None, tmp_path, NOW)
    assert entry["method"] == "persistence"
    assert "over all folds" in entry["reason"]
    assert not model_path(tmp_path, "pm25_h1").exists()


def saved_previous(tmp_path, model, train_end):
    joblib.dump(model, model_path(tmp_path, "pm25_h1"))
    return {
        "method": "candidate",
        "train_end": train_end,
        "promoted_at": NOW,
        "features": ["answer"],
        "candidates": ["candidate"],
    }


def test_model_is_kept_when_too_few_days_are_unseen(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    previous = saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-3].date()))
    entry, _, _ = run(tmp_path, previous)
    assert entry["train_end"] == previous["train_end"]
    assert "unseen" in entry["reason"]


def test_better_candidate_replaces_the_previous_model(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    previous = saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-60].date()))
    entry, _, _ = run(tmp_path, previous)
    assert entry["reason"].startswith("promoted")
    assert entry["train_end"] != previous["train_end"]


def test_previous_model_is_kept_when_it_is_better(monkeypatch, tmp_path):
    use(monkeypatch, OffByFiveModel)
    previous = saved_previous(tmp_path, PerfectModel(), str(INDEX[-60].date()))
    # Baselines must be beaten too, so make them worse than the candidate here.
    features, labels, baselines = inputs()
    baselines = {name: series + 10.0 for name, series in baselines.items()}
    entry, _, _ = train_slot("pm25", 1, features, labels, baselines, previous, tmp_path, NOW)
    assert entry["train_end"] == previous["train_end"]
    assert "previous model" in entry["reason"]
    assert isinstance(joblib.load(model_path(tmp_path, "pm25_h1")), PerfectModel)


def test_report_never_rewards_rows_without_all_methods(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    features, labels, baselines = inputs()
    baselines["seasonal7"] = baselines["seasonal7"].where(INDEX < INDEX[600])
    _, report, frame = train_slot("pm25", 1, features, labels, baselines, None, tmp_path, NOW)
    assert frame.index.max() < INDEX[600]
    assert report["overall"]["candidate"]["n"] == len(frame)


def test_report_is_json_serialisable(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    _, report, _ = run(tmp_path)
    json.dumps(report)


@pytest.mark.parametrize("name", ["gradient_boosting", "random_forest"])
def test_real_candidates_accept_columns_that_are_entirely_missing(name):
    rng = np.random.default_rng(2)
    features = pd.DataFrame({"x": rng.normal(size=200), "empty": np.nan})
    labels = features["x"] * 2
    model = train_module.CANDIDATES[name]().fit(features.iloc[:150], labels.iloc[:150])
    later = features.iloc[150:].assign(empty=1.0)
    assert np.isfinite(model.predict(later)).all()


def monthly_series(pattern_strength):
    index = pd.date_range("2020-01-01", periods=72, freq="MS")
    rng = np.random.default_rng(11)
    seasonal = 20 + 10 * np.sin(2 * np.pi * index.month / 12)
    noise = np.zeros(72)
    for i in range(1, 72):
        noise[i] = pattern_strength * noise[i - 1] + rng.normal(0, 3)
    return pd.Series(seasonal + noise, index=index)


def test_monthly_anomaly_needs_to_beat_climatology():
    entry, report = train_monthly(monthly_series(0.9), 2)
    assert entry["method"] == ("anomaly" if report["anomaly"]["mae"] < report["climatology"]["mae"] else "climatology")
    assert entry["residual_q80"] > 0


def test_monthly_without_enough_history_uses_climatology():
    index = pd.date_range("2024-01-01", periods=6, freq="MS")
    entry, report = train_monthly(pd.Series(10.0, index=index), 2)
    assert entry["method"] == "climatology"
    assert entry["residual_q80"] is None
    assert report["n"] == 0


class GoodLongAgoModel(PerfectModel):
    """Best over all folds, but off by six in the newest 90 days."""

    def predict(self, features):
        late = features.index >= INDEX[-90]
        return features["answer"].to_numpy() + np.where(late, 6.0, 0.0)


class SteadyModel(PerfectModel):
    def predict(self, features):
        return features["answer"].to_numpy() + 2.0


def test_next_candidate_is_tried_when_the_best_overall_fails_the_recent_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(train_module, "CANDIDATES", {"good_long_ago": GoodLongAgoModel, "steady": SteadyModel})
    entry, report, _ = run(tmp_path)
    assert entry["method"] == "steady"
    assert "good_long_ago had the lower MAE" in entry["reason"]
    assert report["best_candidate"] == "steady"
    assert model_path(tmp_path, "pm25_h1").exists()


def test_model_on_other_features_is_replaced_without_waiting_for_unseen_days(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    # Saved before a feature was added: no feature list, and only two unseen days.
    previous = {**saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-3].date())), "features": None}
    entry, _, _ = run(tmp_path, previous)
    assert entry["method"] == "candidate"
    assert entry["features"] == ["answer"]
    assert "replaces a model trained on other features" in entry["reason"]


def test_model_on_other_features_is_kept_when_the_candidate_fails(monkeypatch, tmp_path):
    use(monkeypatch, OffByTenModel)
    previous = {**saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-3].date())), "features": ["old"]}
    entry, _, _ = run(tmp_path, previous)
    assert entry["method"] == "candidate" and entry["features"] == ["old"]
    assert entry["reason"].startswith("kept: candidate")


def test_model_chosen_among_other_methods_is_replaced_without_waiting(monkeypatch, tmp_path):
    use(monkeypatch, PerfectModel)
    # Saved before a new candidate was added: no candidate list, two unseen days.
    previous = saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-3].date()))
    del previous["candidates"]
    entry, _, _ = run(tmp_path, previous)
    assert entry["method"] == "candidate" and entry["candidates"] == ["candidate"]
    assert "replaces a model chosen among other methods" in entry["reason"]


def test_change_candidates_are_tried_only_for_the_first_days():
    assert "random_forest_change" in train_module.candidates_for(1)
    assert "gradient_boosting_change" in train_module.candidates_for(3)
    assert train_module.candidates_for(4, "temp_c") == ["gradient_boosting", "random_forest"]


def test_blends_are_tried_for_pm_three_to_six_days_ahead():
    assert "random_forest_blend" in train_module.candidates_for(4, "pm10")
    assert "gradient_boosting_blend" in train_module.candidates_for(7, "pm25")
    assert not any(n.endswith("_blend") for n in train_module.candidates_for(3, "pm25"))
    assert not any(n.endswith("_blend") for n in train_module.candidates_for(5, "rh_pct"))


def test_blend_is_half_model_and_half_weekly_mean():
    rng = np.random.default_rng(4)
    x = rng.normal(size=300)
    features = pd.DataFrame({"x": x, "pm25_mean7": 20.0})
    features.loc[299, "pm25_mean7"] = np.nan
    labels = pd.Series(30 + 5 * x)
    blend = train_module.make_candidate("random_forest_blend", "pm25").fit(features, labels)
    alone = blend.model_.predict(features)
    predicted = blend.predict(features)
    assert np.allclose(predicted[:299], (alone[:299] + 20.0) / 2)
    # Without a weekly mean the model's forecast is used as it is.
    assert np.isclose(predicted[299], alone[299])


@pytest.mark.parametrize("name", ["gradient_boosting_change", "random_forest_change"])
def test_change_candidate_starts_from_the_last_value(name):
    rng = np.random.default_rng(3)
    # The next value is the last one plus a step the model can learn from x.
    level = rng.uniform(5, 80, 400)
    x = rng.normal(size=400)
    features = pd.DataFrame({"pm25_lag0": level, "pm25_mean3": level, "x": x})
    labels = pd.Series(level + 2 * x)
    model = train_module.make_candidate(name, "pm25").fit(features.iloc[:300], labels.iloc[:300])
    # Levels far outside training still come out near the last value.
    later = features.iloc[300:].assign(pm25_lag0=200.0, pm25_mean3=200.0)
    assert np.abs(model.predict(later) - (200 + 2 * later["x"])).mean() < 2.0


def test_change_candidate_uses_the_recent_mean_when_the_last_day_is_missing():
    features = pd.DataFrame({"pm25_lag0": [10.0, np.nan] * 50, "pm25_mean3": [12.0] * 100, "x": 0.0})
    labels = pd.Series([11.0] * 100)
    model = train_module.make_candidate("random_forest_change", "pm25").fit(features, labels)
    assert np.isfinite(model.predict(features)).all()


def test_next_candidate_replaces_the_previous_model_when_the_best_overall_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(train_module, "CANDIDATES", {"good_long_ago": GoodLongAgoModel, "steady": SteadyModel})
    previous = {**saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-60].date())),
                "candidates": ["good_long_ago", "steady"]}
    entry, report, _ = run(tmp_path, previous)
    assert entry["method"] == "steady" and entry["reason"].startswith("promoted")
    assert report["best_candidate"] == "steady"


def test_previous_model_is_kept_when_no_candidate_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(train_module, "CANDIDATES", {"a": OffByTenModel, "b": OffByTenModel})
    previous = {**saved_previous(tmp_path, OffByFiveModel(), str(INDEX[-60].date())),
                "method": "a", "candidates": ["a", "b"]}
    entry, _, _ = run(tmp_path, previous)
    assert entry["method"] == "a" and entry["reason"].startswith("kept: candidate")


def test_temperature_range_is_fitted_around_the_corrected_forecast(monkeypatch, tmp_path):
    use(monkeypatch, OffByTenModel)
    features, labels, baselines = inputs()
    # Persistence wins and always reads 3 too high; half of that is taken back once 15 days are scored.
    entry, report, _ = train_slot("temp_c", 1, features, labels, baselines, None, tmp_path, NOW)
    assert entry["method"] == "persistence" and entry["bias_correction"] is True
    assert report["bias_correction"]["raw"]["mae"] == pytest.approx(3.0)
    assert report["bias_correction"]["corrected"]["mae_newest_year"] == pytest.approx(1.5, abs=0.1)  # the first 15 days stay uncorrected
    assert entry["residual_q80"] == pytest.approx(1.5)
    pm25, _, _ = train_slot("pm25", 1, features, labels, baselines, None, tmp_path, NOW)
    assert "bias_correction" not in pm25 and pm25["residual_q80"] == pytest.approx(3.0)
