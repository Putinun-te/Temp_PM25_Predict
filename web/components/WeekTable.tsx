"use client";

import { bandFor, STANDARDS, type Pollutant } from "@/lib/aqi";
import { chanceList } from "@/lib/data";
import { dayLabel, fmt, methodName } from "@/lib/format";
import type { ChanceAbove, DailyForecast } from "@/lib/types";
import ChanceLines from "./ChanceLines";
import { useLang } from "./LangProvider";

interface ValueProps {
  value?: number | null;
  low?: number | null;
  high?: number | null;
  method?: string;
  digits?: number;
  /** Chances above the band edges, shown only for slots that publish them. */
  chances?: ChanceAbove[];
  pollutant?: Pollutant;
}

function Value({ value, low, high, method, digits = 1, chances, pollutant }: ValueProps) {
  return (
    <>
      <strong>{fmt(value, digits)}</strong>{" "}
      <span className="range">
        ({fmt(low, digits)}–{fmt(high, digits)})
      </span>
      {pollutant && chances && chances.length > 0 && <ChanceLines pollutant={pollutant} chances={chances} />}
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
                  <Value
                    value={day.pm25}
                    low={day.pm25_low}
                    high={day.pm25_high}
                    method={day.pm25_method}
                    pollutant="pm25"
                    chances={chanceList(day.pm25_p_above, day.pm25_p_above_standard, STANDARDS.pm25)}
                  />
                </td>
                <td>
                  <Value
                    value={day.pm10}
                    low={day.pm10_low}
                    high={day.pm10_high}
                    method={day.pm10_method}
                    pollutant="pm10"
                    chances={chanceList(day.pm10_p_above, day.pm10_p_above_standard, STANDARDS.pm10)}
                  />
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
      {days.some(
        (day) =>
          day.pm25_p_above_standard != null || day.pm10_p_above_standard != null || day.pm25_p_above || day.pm10_p_above,
      ) && (
        <p className="note">{t("chanceAboveNote")}</p>
      )}
    </div>
  );
}
