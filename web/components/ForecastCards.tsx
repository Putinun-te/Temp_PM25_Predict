"use client";

import { bandFor, type Pollutant } from "@/lib/aqi";
import { fmt, methodName } from "@/lib/format";
import type { DailyForecast } from "@/lib/types";
import { AqiBadge } from "./AqiBadge";
import { useLang } from "./LangProvider";

interface CardProps {
  title: string;
  value: number | null | undefined;
  digits?: number;
  unit: string;
  low: number | null | undefined;
  high: number | null | undefined;
  note: string;
  pollutant?: Pollutant;
}

function Card({ title, value, digits = 1, unit, low, high, note, pollutant }: CardProps) {
  const { t } = useLang();
  const band = pollutant ? bandFor(pollutant, value) : null;
  return (
    <div className="card" style={band ? { borderLeft: `6px solid ${band.color}` } : undefined}>
      <div className="label">{title}</div>
      <div className="value">
        {fmt(value, digits)}
        <span className="unit"> {unit}</span>
      </div>
      <div className="range">
        {t("likely")} {fmt(low, digits)} {t("to")} {fmt(high, digits)}
      </div>
      {pollutant && <AqiBadge pollutant={pollutant} value={value} />}
      <div className="method">{note}</div>
    </div>
  );
}

export default function ForecastCards({ days }: { days: DailyForecast[] }) {
  const { t } = useLang();
  return (
    <div className="grid">
      {days.flatMap((day) => {
        const when = `${day.label === "today" ? t("today") : t("tomorrow")}, ${day.date}`;
        const tmdTemperature =
          day.tmd_temp_c !== undefined
            ? `${t("tmd")} ${fmt(day.tmd_temp_c)} °C (${fmt(day.tmd_temp_c_min)}–${fmt(day.tmd_temp_c_max)})`
            : methodName(day.temp_c_method);
        const tmdHumidity =
          day.tmd_rh_pct !== undefined ? `${t("tmd")} ${fmt(day.tmd_rh_pct, 0)} %` : methodName(day.rh_pct_method);
        return [
          <Card key={`${day.date}-pm25`} title={`${when} · PM2.5`} value={day.pm25} unit="µg/m³" low={day.pm25_low} high={day.pm25_high} note={methodName(day.pm25_method)} pollutant="pm25" />,
          <Card key={`${day.date}-pm10`} title={`${when} · PM10`} value={day.pm10} unit="µg/m³" low={day.pm10_low} high={day.pm10_high} note={methodName(day.pm10_method)} pollutant="pm10" />,
          <Card key={`${day.date}-temp`} title={`${when} · ${t("temperature")}`} value={day.temp_c} unit="°C" low={day.temp_c_low} high={day.temp_c_high} note={tmdTemperature} />,
          <Card key={`${day.date}-rh`} title={`${when} · ${t("humidity")}`} value={day.rh_pct} digits={0} unit="%" low={day.rh_pct_low} high={day.rh_pct_high} note={tmdHumidity} />,
        ];
      })}
    </div>
  );
}
