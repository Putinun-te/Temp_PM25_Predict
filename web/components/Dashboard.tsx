"use client";

import { useEffect, useState } from "react";
import { dataBase, dayBeforeForecasts, loadForecast, loadHistory, measuredSeries } from "@/lib/data";
import type { Forecast, Point } from "@/lib/types";
import ForecastCards from "./ForecastCards";
import HistoryChart from "./HistoryChart";
import MonthlyTable from "./MonthlyTable";

interface Series {
  measured: Point[];
  forecasts: Point[];
}

export default function Dashboard() {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
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
  }, []);

  return (
    <>
      <h1>Bangkok PM2.5 forecast</h1>
      <p className="sub">
        {forecast
          ? `For ${forecast.as_of}, generated ${forecast.generated_at.replace("T", " ")}, station data up to ${forecast.latest_data_date}`
          : "Loading…"}
        {forecast && (
          <span className={`badge ${forecast.status}`}>
            {forecast.status === "ok" ? "Data current" : `Data ${forecast.data_age_days} days old`}
          </span>
        )}
      </p>
      {error && <p className="error">Could not load the forecast data ({error}).</p>}

      <h2>Today and tomorrow</h2>
      {forecast && <ForecastCards days={forecast.daily} />}

      <h2>Measured PM2.5 against our forecast</h2>
      <div className="chart">{series && <HistoryChart measured={series.measured} forecasts={series.forecasts} />}</div>
      <p className="note">
        The line is the measured Bangkok daily median from Air4Thai reference stations. Dots are the forecast
        issued one day earlier for that date.
      </p>

      <h2>Next three months</h2>
      {forecast && <MonthlyTable months={forecast.monthly} />}
    </>
  );
}
