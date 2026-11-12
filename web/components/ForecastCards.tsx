import { fmt, methodName, range } from "@/lib/format";
import type { DailyForecast } from "@/lib/types";

interface CardProps {
  title: string;
  value: string;
  unit: string;
  detail: string;
  note: string;
}

function Card({ title, value, unit, detail, note }: CardProps) {
  return (
    <div className="card">
      <div className="label">{title}</div>
      <div className="value">
        {value}
        <span className="unit"> {unit}</span>
      </div>
      <div className="range">{detail}</div>
      <div className="method">{note}</div>
    </div>
  );
}

export default function ForecastCards({ days }: { days: DailyForecast[] }) {
  return (
    <div className="grid">
      {days.flatMap((day) => {
        const when = `${day.label === "today" ? "Today" : "Tomorrow"}, ${day.date}`;
        const tmdTemperature =
          day.tmd_temp_c !== undefined
            ? `TMD ${fmt(day.tmd_temp_c)} °C (${fmt(day.tmd_temp_c_min)} to ${fmt(day.tmd_temp_c_max)})`
            : methodName(day.temp_c_method);
        const tmdHumidity = day.tmd_rh_pct !== undefined ? `TMD ${fmt(day.tmd_rh_pct, 0)} %` : methodName(day.rh_pct_method);
        return [
          <Card key={`${day.date}-pm25`} title={`${when} · PM2.5`} value={fmt(day.pm25)} unit="µg/m³" detail={range(day.pm25_low, day.pm25_high)} note={methodName(day.pm25_method)} />,
          <Card key={`${day.date}-pm10`} title={`${when} · PM10`} value={fmt(day.pm10)} unit="µg/m³" detail={range(day.pm10_low, day.pm10_high)} note={methodName(day.pm10_method)} />,
          <Card key={`${day.date}-temp`} title={`${when} · Temperature`} value={fmt(day.temp_c)} unit="°C" detail={range(day.temp_c_low, day.temp_c_high)} note={tmdTemperature} />,
          <Card key={`${day.date}-rh`} title={`${when} · Humidity`} value={fmt(day.rh_pct, 0)} unit="%" detail={range(day.rh_pct_low, day.rh_pct_high, 0)} note={tmdHumidity} />,
        ];
      })}
    </div>
  );
}
