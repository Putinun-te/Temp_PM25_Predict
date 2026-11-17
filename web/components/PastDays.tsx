"use client";

import { useState } from "react";
import { type Check, matchPercent, recentDayChecks } from "@/lib/accuracy";
import { bandFor } from "@/lib/aqi";
import { fmt } from "@/lib/format";
import type { ScoredForecast } from "@/lib/types";
import { useLang } from "./LangProvider";

const TARGETS = [
  { id: "pm25", name: "PM2.5", unit: "µg/m³", digits: 1 },
  { id: "pm10", name: "PM10", unit: "µg/m³", digits: 1 },
  { id: "temp_c", key: "temperature", unit: "°C", digits: 1 },
  { id: "rh_pct", key: "humidity", unit: "%", digits: 0 },
] as const;
const DAYS = 7;

function Cells({ check, digits }: { check: Check | null; digits: number }) {
  const { t } = useLang();
  if (!check) return <td colSpan={2}>{t("notIssued")}</td>;
  const match = matchPercent(check.percent);
  const sign = check.diff > 0 ? "+" : "";
  return (
    <>
      <td>
        {fmt(check.forecast, digits)} <span className="range">({sign}{fmt(check.diff, digits)})</span>
      </td>
      <td>{match === null ? "n/a" : `${fmt(match, 0)}%`}</td>
    </>
  );
}

/** The newest measured days for one value, each with the forecasts made for it. */
export default function PastDays({ scored }: { scored: ScoredForecast[] }) {
  const { t } = useLang();
  const [target, setTarget] = useState<(typeof TARGETS)[number]["id"]>("pm25");
  const meta = TARGETS.find((item) => item.id === target)!;
  const rows = recentDayChecks(scored, target, DAYS);
  const pollutant = target === "pm25" || target === "pm10" ? target : null;
  return (
    <>
      <div className="lang" role="group" aria-label={t("target")}>
        {TARGETS.map((item) => (
          <button key={item.id} type="button" aria-pressed={target === item.id} className={target === item.id ? "active" : ""} onClick={() => setTarget(item.id)}>
            {"name" in item ? item.name : t(item.key)}
          </button>
        ))}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("date")}</th>
              <th>
                {t("actual")} ({meta.unit})
              </th>
              <th>{t("issuedSameDay")}</th>
              <th>{t("match")}</th>
              <th>{t("issuedDayBefore")}</th>
              <th>{t("match")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const band = pollutant ? bandFor(pollutant, row.actual) : null;
              return (
                <tr key={row.date}>
                  <td>{row.date}</td>
                  <td>
                    {band && <span className="aqi-dot small" style={{ background: band.color }} />}
                    <strong>{fmt(row.actual, meta.digits)}</strong>
                  </td>
                  <Cells check={row.sameDay} digits={meta.digits} />
                  <Cells check={row.dayBefore} digits={meta.digits} />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
