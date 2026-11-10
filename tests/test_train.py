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
    return {"method": "candidate", "train_end": train_end, "promoted_at": NOW}


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
