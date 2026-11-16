"use client";

import { useEffect, useState } from "react";
import { type DayCheck, latestDayChecks } from "@/lib/accuracy";
import { dataBase, dayBeforeForecasts, loadAccuracy, loadForecast, loadHistory, loadHourly, loadStations, measuredSeries } from "@/lib/data";
import type { Forecast, HourlyForecast, Point, StationsFile } from "@/lib/types";
import { AqiLegend } from "./AqiBadge";
import ForecastCards from "./ForecastCards";
import GistdaReference from "./GistdaReference";
import HistoryChart from "./HistoryChart";
import { useLang } from "./LangProvider";
import MonthlyTable from "./MonthlyTable";
import HourlyChart from "./HourlyChart";
import StationMap, { type MapMode } from "./StationMap";
import YesterdayCards from "./YesterdayCards";

interface Series {
  measured: Point[];
  forecasts: Point[];
}

export default function Dashboard() {
  const { t } = useLang();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [stations, setStations] = useState<StationsFile | null>(null);
  const [checks, setChecks] = useState<DayCheck[]>([]);
  const [hourly, setHourly] = useState<HourlyForecast | null>(null);
  const [mapMode, setMapMode] = useState<MapMode>("measured");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const base = dataBase(window.location.search);
    loadForecast(base)
      .then((loaded) => {
        setForecast(loaded);
        return loadHistory(base);
      })
      .then(({ daily, history }) => {
        const measured = measuredSeries(daily);
        setSeries({ measured, forecasts: dayBeforeForecasts(history, measured) });
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
    loadStations(base).then(setStations);
    loadHourly(base).then(setHourly);
    loadAccuracy(base).then(({ scored }) => setChecks(latestDayChecks(scored)));
  }, []);

  return (
    <>
      <h1>{t("title")}</h1>
      <p className="sub">
        {forecast
          ? `${t("forDate")} ${forecast.as_of}, ${t("generated")} ${forecast.generated_at.replace("T", " ")}, ${t("dataUpTo")} ${forecast.latest_data_date}`
          : t("loading")}
        {forecast && (
          <span className={`badge ${forecast.status}`}>
            {forecast.status === "ok" ? t("dataCurrent") : `${t("dataOld")} ${forecast.data_age_days} ${t("daysOld")}`}
          </span>
        )}
      </p>
      {error && (
        <p className="error">
          {t("loadError")} ({error}).
        </p>
      )}

      <h2>{t("todayTomorrow")}</h2>
      {forecast && <ForecastCards days={forecast.daily} />}
      {forecast?.gistda && <GistdaReference data={forecast.gistda} />}
      <AqiLegend />

      {hourly && hourly.as_of === forecast?.as_of && (
        <>
          <h2>{t("hourlyTitle")}</h2>
          <div className="chart">
            <HourlyChart
              data={hourly}
              labels={{ measured: t("measured"), forecast: t("hourlyForecast"), range: t("hourlyRange") }}
            />
          </div>
          <p className="note">{t("hourlyNote")}</p>
        </>
      )}

      {checks.length > 0 && (
        <>
          <h2>{t("yesterdayTitle")}</h2>
          <YesterdayCards checks={checks} />
          <p className="note">{t("yesterdayNote")}</p>
        </>
      )}

      <h2>{t("measuredVsForecast")}</h2>
      <div className="chart">
        {series && (
          <HistoryChart
            measured={series.measured}
            forecasts={series.forecasts}
            labels={{ measured: t("measured"), forecast: t("forecastDayBefore") }}
          />
        )}
      </div>
      <p className="note">{t("chartNote")}</p>

      {stations && (
        <>
          <h2>{t("stationsTitle")}</h2>
          {forecast?.station_forecasts && (
            <div className="lang" role="group" aria-label={t("stationsTitle")}>
              {(["measured", "today", "tomorrow"] as const).map((mode) => (
                <button key={mode} type="button" aria-pressed={mapMode === mode} className={mapMode === mode ? "active" : ""} onClick={() => setMapMode(mode)}>
                  {t(mode === "measured" ? "mapMeasured" : mode === "today" ? "mapToday" : "mapTomorrow")}
                </button>
              ))}
            </div>
          )}
          <StationMap data={stations} forecasts={forecast?.station_forecasts} mode={mapMode} />
          <p className="note">{t("mapNote")}</p>
        </>
      )}

      <h2>{t("nextMonths")}</h2>
      {forecast && <MonthlyTable months={forecast.monthly} />}
    </>
  );
}
