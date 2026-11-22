import pandas as pd

from pm25.features import EXOGENOUS_COLUMNS
from pm25.served import append_served, compare_served, differing, served_rows


def inputs(days=60):
    index = pd.date_range("2026-09-01", periods=days, freq="D", name="date")
    targets = pd.DataFrame({"pm25": range(days), "pm10": range(10, 10 + days)}, index=index, dtype=float)
    exogenous = pd.DataFrame({name: 1.0 for name in EXOGENOUS_COLUMNS}, index=index)
    return targets, exogenous


def test_served_rows_are_kept_per_day_and_horizon(tmp_path):
    targets, exogenous = inputs()
    as_of = pd.Timestamp("2026-10-20")
    rows = served_rows(targets, exogenous, as_of)
    assert list(rows["horizon"]) == list(range(1, 8)) and set(rows["as_of"]) == {"2026-10-20"}
    assert rows.loc[0, "pm25_lag0"] == targets.loc["2026-10-19", "pm25"]
    path = tmp_path / "served.csv"
    append_served(path, rows)
    append_served(path, rows)  # A rerun replaces the day
    assert len(pd.read_csv(path)) == 7


def test_inputs_that_changed_after_the_forecast_are_reported():
    targets, exogenous = inputs()
    as_of = pd.Timestamp("2026-10-20")
    served = served_rows(targets, exogenous, as_of)
    # At forecast time yesterday's PM2.5 was missing; it arrived later.
    served["pm25_lag0"] = float("nan")
    check = compare_served(served, targets, exogenous, pd.Timestamp("2026-10-21"))
    assert check["forecasts"] == 1
    names = [f["feature"] for f in differing(check)]
    assert names[0] == "pm25_lag0"
    assert next(f for f in check["features"] if f["feature"] == "pm25_lag0")["missing_at_forecast"] == 7
    # Unchanged inputs are compared and match.
    assert next(f for f in check["features"] if f["feature"] == "pm10_lag0")["changed"] == 0
