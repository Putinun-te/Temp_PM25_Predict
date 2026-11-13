"use client";

import { useEffect, useState } from "react";
import { dataBase, dayBeforeForecasts, loadForecast, loadHistory, loadStations, measuredSeries } from "@/lib/data";
import type { Forecast, Point, StationsFile } from "@/lib/types";
import { AqiLegend } from "./AqiBadge";
import ForecastCards from "./ForecastCards";
import HistoryChart from "./HistoryChart";
import { useLang } from "./LangProvider";
import MonthlyTable from "./MonthlyTable";
import StationMap from "./StationMap";

interface Series {
  measured: Point[];
  forecasts: Point[];
}

export default function Dashboard() {
  const { t } = useLang();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [stations, setStations] = useState<StationsFile | null>(null);
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
      <AqiLegend />

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
