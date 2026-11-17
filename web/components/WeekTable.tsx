"use client";

import { bandFor } from "@/lib/aqi";
import { dayLabel, fmt, methodName } from "@/lib/format";
import type { DailyForecast } from "@/lib/types";
import { useLang } from "./LangProvider";

function Value({ value, low, high, method, digits = 1 }: { value?: number | null; low?: number | null; high?: number | null; method?: string; digits?: number }) {
  return (
    <>
      <strong>{fmt(value, digits)}</strong>{" "}
      <span className="range">
        ({fmt(low, digits)}–{fmt(high, digits)})
      </span>
      <div className="method">{methodName(method)}</div>
    </>
  );
}

/** Every daily forecast in one table, today first. */
export default function WeekTable({ days }: { days: DailyForecast[] }) {
  const { lang, t } = useLang();
  const weekday = new Intl.DateTimeFormat(lang === "th" ? "th-TH" : "en-GB", { weekday: "short", timeZone: "UTC" });
  return (
    <div className="table-wrap">
      <table className="week">
        <thead>
          <tr>
            <th>{t("day")}</th>
            <th>PM2.5 (µg/m³)</th>
            <th>PM10 (µg/m³)</th>
            <th>{t("temperature")} (°C)</th>
            <th>{t("humidity")} (%)</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => {
            const band = bandFor("pm25", day.pm25);
            return (
              <tr key={day.date}>
                <td>
                  <strong>{dayLabel(day.label, t)}</strong>
                  <div className="method">
                    {weekday.format(new Date(`${day.date}T00:00:00Z`))} {day.date}
                  </div>
                </td>
                <td>
                  {band && <span className="aqi-dot small" style={{ background: band.color }} title={lang === "th" ? band.th : band.en} />}
                  <Value value={day.pm25} low={day.pm25_low} high={day.pm25_high} method={day.pm25_method} />
                </td>
                <td>
                  <Value value={day.pm10} low={day.pm10_low} high={day.pm10_high} method={day.pm10_method} />
                </td>
                <td>
                  <Value value={day.temp_c} low={day.temp_c_low} high={day.temp_c_high} method={day.temp_c_method} />
                </td>
                <td>
                  <Value value={day.rh_pct} low={day.rh_pct_low} high={day.rh_pct_high} method={day.rh_pct_method} digits={0} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
