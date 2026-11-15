"use client";

import { useEffect, useState } from "react";
import { type DayCheck, latestDayChecks } from "@/lib/accuracy";
import { dataBase, dayBeforeForecasts, loadAccuracy, loadForecast, loadHistory, loadStations, measuredSeries } from "@/lib/data";
import type { Forecast, Point, StationsFile } from "@/lib/types";
import { AqiLegend } from "./AqiBadge";
import ForecastCards from "./ForecastCards";
import GistdaReference from "./GistdaReference";
import HistoryChart from "./HistoryChart";
import { useLang } from "./LangProvider";
import MonthlyTable from "./MonthlyTable";
import StationMap from "./StationMap";
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
          <h2>{t("stationsMap")}</h2>
          <StationMap data={stations} />
          <p className="note">{t("mapNote")}</p>
        </>
      )}

      <h2>{t("nextMonths")}</h2>
      {forecast && <MonthlyTable months={forecast.monthly} />}
    </>
  );
}
