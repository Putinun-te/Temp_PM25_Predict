"use client";

import { type Check, type DayCheck, matchPercent } from "@/lib/accuracy";
import { bandFor } from "@/lib/aqi";
import { fmt } from "@/lib/format";
import { AqiBadge } from "./AqiBadge";
import { useLang } from "./LangProvider";

const META: Record<string, { name?: string; key?: "temperature" | "humidity"; unit: string; digits: number }> = {
  pm25: { name: "PM2.5", unit: "µg/m³", digits: 1 },
  pm10: { name: "PM10", unit: "µg/m³", digits: 1 },
  temp_c: { key: "temperature", unit: "°C", digits: 1 },
  rh_pct: { key: "humidity", unit: "%", digits: 0 },
};

function Line({ label, check, digits, unit }: { label: string; check: Check | null; digits: number; unit: string }) {
  const { t } = useLang();
  if (!check) {
    return (
      <div className="range">
        {label}: {t("notIssued")}
      </div>
    );
  }
  const size = Math.abs(check.diff);
  const exact = Number(size.toFixed(digits)) === 0;
  const match = matchPercent(check.percent);
  return (
    <div className="range">
      {label}: <strong className="check-value">{fmt(check.forecast, digits)}</strong>
      {match !== null && (
        <>
          {" · "}
          <strong className="check-value">
            {t("match")} {fmt(match, 0)}%
          </strong>
        </>
      )}
      {" · "}
      {exact ? t("exact") : `${check.diff > 0 ? t("tooHigh") : t("tooLow")} ${fmt(size, digits)} ${unit}`}
    </div>
  );
}

export default function YesterdayCards({ checks }: { checks: DayCheck[] }) {
  const { t } = useLang();
  return (
    <div className="grid">
      {checks.map((item) => {
        const meta = META[item.target];
        if (!meta) return null;
        const pollutant = item.target === "pm25" || item.target === "pm10" ? item.target : null;
        const band = pollutant ? bandFor(pollutant, item.actual) : null;
        return (
          <div key={item.target} className="card" style={band ? { borderLeft: `6px solid ${band.color}` } : undefined}>
            <div className="label">
              {item.date} · {meta.name ?? t(meta.key!)} · {t("measuredOn")}
            </div>
            <div className="value">
              {fmt(item.actual, meta.digits)}
              <span className="unit"> {meta.unit}</span>
            </div>
            <Line label={t("issuedSameDay")} check={item.sameDay} digits={meta.digits} unit={meta.unit} />
            <Line label={t("issuedDayBefore")} check={item.dayBefore} digits={meta.digits} unit={meta.unit} />
            {pollutant && <AqiBadge pollutant={pollutant} value={item.actual} />}
          </div>
        );
      })}
    </div>
  );
}
