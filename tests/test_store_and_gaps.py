import pandas as pd

from pm25.ingest import HOUR, TIME, find_gaps, load_series, upsert


def utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def hours(first: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(utc(first), periods=periods, freq="h")


def test_no_gap_when_series_is_complete():
    assert find_gaps(hours("2024-01-01 00:00", 5), utc("2024-01-01 00:00"), utc("2024-01-01 04:00"), HOUR) == []


def test_interior_gap_has_exclusive_bounds():
    times = list(hours("2024-01-01 00:00", 2)) + list(hours("2024-01-01 05:00", 2))
    gaps = find_gaps(times, utc("2024-01-01 00:00"), utc("2024-01-01 06:00"), HOUR)
    assert gaps == [(utc("2024-01-01 01:00"), utc("2024-01-01 05:00"))]


def test_head_and_tail_are_gaps():
    gaps = find_gaps(hours("2024-01-01 02:00", 1), utc("2024-01-01 00:00"), utc("2024-01-01 04:00"), HOUR)
    assert gaps == [
        (utc("2023-12-31 23:00"), utc("2024-01-01 02:00")),
        (utc("2024-01-01 02:00"), utc("2024-01-01 05:00")),
    ]


def test_empty_series_is_one_gap_covering_the_window():
    gaps = find_gaps([], utc("2024-01-01 00:00"), utc("2024-01-01 04:00"), HOUR)
    assert gaps == [(utc("2023-12-31 23:00"), utc("2024-01-01 05:00"))]


def test_jitter_within_tolerance_is_not_a_gap():
    step = pd.Timedelta(minutes=5)
    times = [utc("2024-01-01 00:00:00"), utc("2024-01-01 00:06:00"), utc("2024-01-01 00:11:00")]
    assert find_gaps(times, utc("2024-01-01 00:00:00"), utc("2024-01-01 00:11:00"), step) == []


def test_upsert_is_idempotent(tmp_path):
    path = tmp_path / "series.csv"
    frame = pd.DataFrame({TIME: hours("2024-01-01 00:00", 3), "value": [1.0, 2.0, 3.0]})
    assert upsert(path, frame) == 3
    assert upsert(path, frame) == 0
    assert len(load_series(path)) == 3


def test_upsert_replaces_on_conflict_and_sorts(tmp_path):
    path = tmp_path / "series.csv"
    upsert(path, pd.DataFrame({TIME: hours("2024-01-01 01:00", 1), "value": [1.0]}))
    upsert(path, pd.DataFrame({TIME: hours("2024-01-01 00:00", 2), "value": [5.0, 9.0]}))
    stored = load_series(path)
    assert stored["value"].tolist() == [5.0, 9.0]
    assert stored[TIME].is_monotonic_increasing


def test_upsert_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "series.csv"
    upsert(path, pd.DataFrame({TIME: hours("2024-01-01 00:00", 1), "value": [1.0]}))
    assert [item.name for item in tmp_path.iterdir()] == ["series.csv"]
