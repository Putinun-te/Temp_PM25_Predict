"""Turn stored hourly data into daily targets and leakage-free features.

A row is indexed by its forecast origin: the last complete local day whose data
may be used. Features only look at the origin and earlier. Labels sit `horizon`
days after the origin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pm25.ingest import PARAMETER, SENSOR, TIME, VALUE

TIMEZONE = "Asia/Bangkok"
TARGETS = ("pm25", "pm10")
# Weather targets come from Open-Meteo history, a model reanalysis, not a station.
WEATHER_TARGETS = ("temp_c", "rh_pct")
ALL_TARGETS = TARGETS + WEATHER_TARGETS
UNITS = {"pm25": "ug/m3", "pm10": "ug/m3", "temp_c": "C", "rh_pct": "%"}
MIN_HOURS_PER_DAY = 18
MIN_STATIONS = {"pm25": 5, "pm10": 2}
MIN_DAYS_PER_MONTH = 20

TARGET_LAGS = (0, 1, 2, 6, 13)
TARGET_ROLLING_WINDOWS = (3, 7, 14)
EXOGENOUS_COLUMNS = (
    "om_pm25",
    "om_no2",
    "om_o3",
    "om_so2",
    "om_co",
    "temp_c",
    "rh_pct",
    "precip_mm",
    "wind_kmh",
    "wind_u",
    "wind_v",
    # NASA FIRMS fire detections, missing when no FIRMS_MAP_KEY is configured.
    "fire_count",
    "fire_frp",
)
# Features added after the first models were saved. A model saved without a
# feature list was trained without these, so they are left out when it predicts.
LATER_FEATURE_PREFIXES = ("fire_",)


def _local_date(times: pd.Series) -> pd.Series:
    return times.dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize()


def daily_targets(openaq: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return the Bangkok daily value: the median across the station panel.

    A station-day needs enough hours to be representative, and a city-day needs
    enough stations. Days before `as_of` only, because the current day is still
    incomplete. The median resists one station reading abnormally.
    """
    frame = openaq.assign(date=_local_date(openaq[TIME]))
    frame = frame[frame["date"] < as_of]
    station_days = (
        frame.groupby([PARAMETER, SENSOR, "date"])[VALUE].agg(["mean", "count"]).reset_index()
    )
    station_days = station_days[station_days["count"] >= MIN_HOURS_PER_DAY]
    city_days = (
        station_days.groupby([PARAMETER, "date"])["mean"]
        .agg(["median", "count"])
        .reset_index()
    )
    city_days = city_days[city_days["count"] >= city_days[PARAMETER].map(MIN_STATIONS)]
    wide = city_days.pivot(index="date", columns=PARAMETER, values="median")
    wide = wide.reindex(columns=list(TARGETS))
    calendar = pd.date_range(frame["date"].min(), as_of - pd.Timedelta(days=1), freq="D", name="date")
    wide = wide.reindex(calendar)
    wide.columns.name = None
    return wide


def _complete_days(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    frame = frame.assign(date=_local_date(frame[TIME]))
    frame = frame[frame["date"] < as_of]
    counts = frame.groupby("date")[TIME].transform("size")
    return frame[counts >= MIN_HOURS_PER_DAY]


def daily_exogenous(
    air_quality: pd.DataFrame,
    weather: pd.DataFrame,
    as_of: pd.Timestamp,
    fires: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return daily Open-Meteo features.

    Modelled PM10 is left out on purpose: its ratio to PM2.5 changes abruptly in
    November 2024, so it does not mean the same thing across the whole history.
    """
    air = _complete_days(air_quality, as_of)
    air_daily = air.groupby("date")[["om_pm25", "om_no2", "om_o3", "om_so2", "om_co"]].mean()

    wx = _complete_days(weather, as_of)
    radians = np.deg2rad(wx["om_wind_deg"])
    wx = wx.assign(
        wind_u=-wx["om_wind_kmh"] * np.sin(radians),
        wind_v=-wx["om_wind_kmh"] * np.cos(radians),
    )
    wx_daily = wx.groupby("date").agg(
        temp_c=("om_temp_c", "mean"),
        rh_pct=("om_rh_pct", "mean"),
        precip_mm=("om_precip_mm", "sum"),
        wind_kmh=("om_wind_kmh", "mean"),
        wind_u=("wind_u", "mean"),
        wind_v=("wind_v", "mean"),
    )
    daily = air_daily.join(wx_daily, how="outer")
    if fires is not None and not fires.empty:
        daily = daily.join(fires[fires.index < as_of], how="left")
    return daily.reindex(columns=list(EXOGENOUS_COLUMNS))


def with_weather_targets(targets: pd.DataFrame, exogenous: pd.DataFrame) -> pd.DataFrame:
    """Add daily temperature and humidity as extra targets on the same calendar."""
    weather = exogenous.reindex(columns=list(WEATHER_TARGETS)).reindex(targets.index)
    return targets.join(weather)


def build_features(
    targets: pd.DataFrame, exogenous: pd.DataFrame, horizon: int
) -> pd.DataFrame:
    """Return one row per origin day, using only information known at that origin.

    The index is a continuous calendar, so a lag always means calendar days even
    when data is missing. Missing inputs stay NaN.
    """
    index = targets.index
    exogenous = exogenous.reindex(index)
    columns: dict[str, pd.Series] = {}

    for name in TARGETS:
        series = targets[name]
        for lag in TARGET_LAGS:
            columns[f"{name}_lag{lag}"] = series.shift(lag)
        for window in TARGET_ROLLING_WINDOWS:
            columns[f"{name}_mean{window}"] = series.rolling(
                window, min_periods=max(2, window // 2)
            ).mean()

    for name in EXOGENOUS_COLUMNS:
        series = exogenous[name]
        columns[f"{name}_lag0"] = series
        columns[f"{name}_lag1"] = series.shift(1)
        columns[f"{name}_mean3"] = series.rolling(3, min_periods=2).mean()

    target_dates = index + pd.Timedelta(days=horizon)
    columns["doy_sin"] = pd.Series(np.sin(2 * np.pi * target_dates.day_of_year / 365.25), index=index)
    columns["doy_cos"] = pd.Series(np.cos(2 * np.pi * target_dates.day_of_year / 365.25), index=index)
    columns["dow_sin"] = pd.Series(np.sin(2 * np.pi * target_dates.day_of_week / 7), index=index)
    columns["dow_cos"] = pd.Series(np.cos(2 * np.pi * target_dates.day_of_week / 7), index=index)
    return pd.DataFrame(columns, index=index)


def model_inputs(features: pd.DataFrame, entry: dict) -> pd.DataFrame:
    """Return the feature columns a saved model was trained on, in training order."""
    names = entry.get("features")
    if names is None:
        names = [c for c in features.columns if not c.startswith(LATER_FEATURE_PREFIXES)]
    return features.reindex(columns=names)


def build_labels(targets: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return the value `horizon` days after each origin."""
    return targets.shift(-horizon)


def daily_baselines(series: pd.Series, horizon: int) -> dict[str, pd.Series]:
    """Return naive forecasts for each origin: last value, and same weekday one week earlier."""
    return {"persistence": series, "seasonal7": series.shift(7 - horizon)}


def monthly_targets(targets: pd.DataFrame) -> pd.DataFrame:
    """Return monthly means, leaving months with too few valid days as NaN."""
    grouped = targets.groupby(targets.index.to_period("M"))
    monthly = grouped.mean().where(grouped.count() >= MIN_DAYS_PER_MONTH)
    monthly.index = monthly.index.to_timestamp()
    return monthly


def monthly_forecast(
    history: pd.Series, target_month: pd.Timestamp, horizon: int
) -> dict[str, float]:
    """Return climatology and damped-anomaly forecasts from months before the origin.

    Climatology is the historical mean of the same calendar month. The anomaly
    method adds how unusual the origin month was, shrunk towards zero with
    distance by the month-to-month persistence seen in the history.
    """
    known = history.dropna()
    climatology_by_month = known.groupby(known.index.month).mean()
    climatology = float(climatology_by_month.get(target_month.month, np.nan))

    anomalies = known - known.index.month.map(climatology_by_month).to_numpy()
    calendar = pd.date_range(history.index.min(), history.index.max(), freq="MS")
    autocorrelation = anomalies.reindex(calendar).autocorr(1)
    persistence = float(np.clip(autocorrelation, 0.0, 1.0)) if np.isfinite(autocorrelation) else 0.0

    origin = target_month - pd.DateOffset(months=horizon)
    origin_anomaly = anomalies.get(origin, np.nan)
    adjustment = 0.0 if pd.isna(origin_anomaly) else persistence**horizon * float(origin_anomaly)
    return {"climatology": climatology, "anomaly": climatology + adjustment}
