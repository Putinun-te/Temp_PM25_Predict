"use client";

import { bandFor } from "@/lib/aqi";
import { fmt } from "@/lib/format";
import type { MonthlyForecast } from "@/lib/types";
import { useLang } from "./LangProvider";

export default function MonthlyTable({ months }: { months: MonthlyForecast[] }) {
  const { t } = useLang();
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t("month")}</th>
            <th>PM2.5 (µg/m³)</th>
            <th>PM10 (µg/m³)</th>
            <th>{t("temperature")} (°C)</th>
            <th>{t("humidity")} (%)</th>
          </tr>
        </thead>
        <tbody>
          {months.map((month) => {
            const band = bandFor("pm25", month.pm25);
            return (
              <tr key={month.month}>
                <td>{month.month}</td>
                <td>
                  {band && <span className="aqi-dot small" style={{ background: band.color }} aria-hidden="true" />}
                  {fmt(month.pm25)}{" "}
                  <span className="range">
                    ({fmt(month.pm25_low)}–{fmt(month.pm25_high)})
                  </span>
                </td>
                <td>{fmt(month.pm10)}</td>
                <td>{fmt(month.temp_c)}</td>
                <td>{fmt(month.rh_pct, 0)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
