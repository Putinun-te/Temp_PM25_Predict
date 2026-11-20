"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AqiBadge } from "./AqiBadge";
import { useLang } from "./LangProvider";
import StationChart, { type StationSeries } from "./StationChart";
import { STANDARDS } from "@/lib/aqi";
import ChanceLines from "./ChanceLines";
import {
  chanceList,
  dataBase,
  forecastDates,
  loadForecast,
  loadStations,
  loadStationScores,
  stationIdFrom,
  summarizeStation,
} from "@/lib/data";
import { dayLabel, fmt, methodName } from "@/lib/format";
import { DAY_LABELS, type Forecast, type HourlyTarget, type ScoredStationForecast, type StationsFile } from "@/lib/types";

interface Loaded {
  forecast: Forecast;
  stations: StationsFile;
  scores: ScoredStationForecast[];
}

/** The station's forecast for one day and target: value, low, high, method and chance above the standard. */
function dayValue(loaded: Loaded, id: number, label: (typeof DAY_LABELS)[number], target: HourlyTarget) {
  const entry = loaded.forecast.station_forecasts?.find((item) => item.location_id === id)?.[label];
  if (!entry) return null;
  if (target === "pm10") {
    const pm10 = entry.pm10;
    return pm10
      ? {
          value: pm10.pm10,
          low: pm10.low,
          high: pm10.high,
          method: pm10.method,
          chances: chanceList(pm10.p_above, pm10.p_above_standard, STANDARDS.pm10),
        }
      : null;
  }
  return {
    value: entry.pm25,
    low: entry.low,
    high: entry.high,
    method: entry.method,
    chances: chanceList(entry.p_above, entry.p_above_standard, STANDARDS.pm25),
  };
}

export default function StationView() {
  const { t } = useLang();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState(false);
  const [id, setId] = useState<number | null>(null);
  const [target, setTarget] = useState<HourlyTarget>("pm25");

  useEffect(() => {
    const search = window.location.search;
    setId(stationIdFrom(search));
    const base = dataBase(search);
    Promise.all([loadForecast(base), loadStations(base), loadStationScores(base)])
      .then(([forecast, stations, scores]) => {
        if (!stations) throw new Error("stations.json missing");
        setLoaded({ forecast, stations, scores });
      })
      .catch(() => setError(true));
  }, []);

  const station = loaded?.stations.stations.find((item) => item.location_id === id) ?? null;
  const hasPm10 = Boolean(station?.pm10);
  const shown: HourlyTarget = target === "pm10" && hasPm10 ? "pm10" : "pm25";

  const series = useMemo<StationSeries | null>(() => {
    if (!loaded || !station || id === null) return null;
    const past = loaded.stations.dates;
    const ahead = forecastDates(loaded.forecast.as_of).filter((date) => !past.includes(date));
    const dates = [...past, ...ahead];
    const measured = [...(station[shown] ?? past.map(() => null)), ...ahead.map(() => null)];
    // Forecasts made the day before for days the station has already measured.
    const dayBefore = dates.map((date) => {
      const row = loaded.scores.find(
        (item) => item.location_id === id && item.target === shown && item.label === "tomorrow" && item.period === date,
      );
      return row?.forecast ?? null;
    });
    const byDate = new Map(
      DAY_LABELS.map((label, i) => [forecastDates(loaded.forecast.as_of)[i], dayValue(loaded, id, label, shown)]),
    );
    const pick = (key: "value" | "low" | "high") => dates.map((date) => byDate.get(date)?.[key] ?? null);
    return { dates, measured, dayBefore, forecast: pick("value"), low: pick("low"), high: pick("high") };
  }, [loaded, station, id, shown]);

  if (error) return <p className="error">{t("loadError")}</p>;
  if (!loaded) return <p className="sub">{t("loading")}</p>;

  const summary = id === null ? null : summarizeStation(loaded.scores, id, shown);
  // Older forecasts, and slots that did not earn it, have no chance above the standard.
  const hasChance = id !== null && DAY_LABELS.some((label) => (dayValue(loaded, id, label, shown)?.chances.length ?? 0) > 0);
  const choose = (next: number) => {
    setId(next);
    const params = new URLSearchParams(window.location.search);
    params.set("id", String(next));
    window.history.replaceState(null, "", `?${params.toString()}`);
  };

  return (
    <>
      <p className="sub">
        <Link href="/">{t("backToMap")}</Link>
      </p>
      <label className="station-pick">
        {t("stationPick")}{" "}
        <select value={id ?? ""} onChange={(event) => choose(Number(event.target.value))}>
          <option value="" disabled>
            …
          </option>
          {[...loaded.stations.stations]
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((item) => (
              <option key={item.location_id} value={item.location_id}>
                {item.name}
              </option>
            ))}
        </select>
      </label>
      {!station || id === null ? (
        <p className="note">{t("stationNotFound")}</p>
      ) : (
        <>
          <h1>{station.name}</h1>
          <p className="sub">
            {station.locality} · {station.latitude.toFixed(3)}, {station.longitude.toFixed(3)}
          </p>
          {hasPm10 && (
            <div className="lang" role="group" aria-label={t("stationChartTitle")} style={{ marginTop: 16 }}>
              {(["pm25", "pm10"] as const).map((option) => (
                <button key={option} className={shown === option ? "active" : ""} onClick={() => setTarget(option)}>
                  {option === "pm25" ? "PM2.5" : "PM10"}
                </button>
              ))}
            </div>
          )}
          <h2>{t("stationChartTitle")}</h2>
          {series && (
            <div className="chart">
              <StationChart
                series={series}
                target={shown}
                labels={{ measured: t("measuredOn"), forecast: t("stationForecastTitle"), range: t("hourlyRange"), dayBefore: t("forecastDayBefore") }}
              />
            </div>
          )}
          <p className="note">{t("stationNote")}</p>

          <h2>{t("stationForecastTitle")}</h2>
          <div className="table-wrap">
            <table className="week">
              <thead>
                <tr>
                  <th>{t("date")}</th>
                  <th>{shown === "pm25" ? "PM2.5" : "PM10"} (µg/m³)</th>
                  {hasChance && <th>{t("chanceAbove")}</th>}
                </tr>
              </thead>
              <tbody>
                {DAY_LABELS.map((label, i) => {
                  const value = dayValue(loaded, id, label, shown);
                  return (
                    <tr key={label}>
                      <td>
                        <strong>{dayLabel(label, t)}</strong>
                        <div className="method">{forecastDates(loaded.forecast.as_of)[i]}</div>
                      </td>
                      <td>
                        {value && value.value !== null ? (
                          <>
                            <strong>{fmt(value.value)}</strong> <span className="range">({fmt(value.low)}–{fmt(value.high)})</span>
                            <AqiBadge pollutant={shown} value={value.value} />
                            <div className="method">{methodName(value.method)}</div>
                          </>
                        ) : (
                          t("noData")
                        )}
                      </td>
                      {hasChance && <td>{value && <ChanceLines pollutant={shown} chances={value.chances} />}</td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {hasChance && <p className="note">{t("chanceAboveNote")}</p>}

          <h2>{t("stationAccuracyTitle")}</h2>
          {summary && summary.days > 0 ? (
            <div className="grid">
              <div className="card">
                <div className="label">{t("scoredDays")}</div>
                <div className="value">{summary.days}</div>
              </div>
              <div className="card">
                <div className="label">MAE</div>
                <div className="value">
                  {fmt(summary.mae)} <span className="unit">µg/m³</span>
                </div>
              </div>
              <div className="card">
                <div className="label">{t("baselineMae")}</div>
                <div className="value">
                  {fmt(summary.baselineMae)} <span className="unit">µg/m³</span>
                </div>
              </div>
              <div className="card">
                <div className="label">{t("withinRange")}</div>
                <div className="value">{summary.coverage === null ? "n/a" : `${Math.round(summary.coverage * 100)}%`}</div>
              </div>
            </div>
          ) : (
            <p className="note">{t("stationNoScores")}</p>
          )}
          <p className="note">{t("stationAccuracyNote")}</p>
          <p className="note">OpenAQ location {station.location_id}</p>
        </>
      )}
    </>
  );
}
