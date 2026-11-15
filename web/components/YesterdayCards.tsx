"use client";

import type { Check, DayCheck } from "@/lib/accuracy";
import { bandFor } from "@/lib/aqi";
import { fmt } from "@/lib/format";
import { AqiBadge } from "./AqiBadge";
import { useLang } from "./LangProvider";

const META: Record<string, { name?: string; key?: "temperature" | "humidity"; unit: string; digits: number; percent: boolean }> = {
  pm25: { name: "PM2.5", unit: "µg/m³", digits: 1, percent: true },
  pm10: { name: "PM10", unit: "µg/m³", digits: 1, percent: true },
  // A percentage of degrees Celsius or of relative humidity misleads, so these show the difference only.
  temp_c: { key: "temperature", unit: "°C", digits: 1, percent: false },
  rh_pct: { key: "humidity", unit: "%", digits: 0, percent: false },
};

function Line({ label, check, digits, unit, percent }: { label: string; check: Check | null; digits: number; unit: string; percent: boolean }) {
  const { t } = useLang();
  if (!check) {
    return (
      <div className="range">
        {label}: {t("notIssued")}
      </div>
    );
  }
  const size = Math.abs(check.diff);
  const rounded = Number(size.toFixed(digits));
  const verdict =
    rounded === 0
      ? t("exact")
      : `${check.diff > 0 ? t("tooHigh") : t("tooLow")} ${fmt(size, digits)} ${unit}${
          percent && check.percent !== null ? ` (${fmt(check.percent, 0)}%)` : ""
        }`;
  return (
    <div className="range">
      {label}: <strong className="check-value">{fmt(check.forecast, digits)}</strong> · {verdict}
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
            <Line label={t("issuedSameDay")} check={item.sameDay} digits={meta.digits} unit={meta.unit} percent={meta.percent} />
            <Line label={t("issuedDayBefore")} check={item.dayBefore} digits={meta.digits} unit={meta.unit} percent={meta.percent} />
            {pollutant && <AqiBadge pollutant={pollutant} value={item.actual} />}
          </div>
        );
      })}
    </div>
  );
}
