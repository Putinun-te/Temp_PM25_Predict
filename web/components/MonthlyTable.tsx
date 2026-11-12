import { fmt } from "@/lib/format";
import type { MonthlyForecast } from "@/lib/types";

export default function MonthlyTable({ months }: { months: MonthlyForecast[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Month</th>
          <th>PM2.5 (µg/m³)</th>
          <th>PM10 (µg/m³)</th>
          <th>Temperature (°C)</th>
          <th>Humidity (%)</th>
        </tr>
      </thead>
      <tbody>
        {months.map((month) => (
          <tr key={month.month}>
            <td>{month.month}</td>
            <td>
              {fmt(month.pm25)}{" "}
              <span className="range">
                ({fmt(month.pm25_low)} to {fmt(month.pm25_high)})
              </span>
            </td>
            <td>{fmt(month.pm10)}</td>
            <td>{fmt(month.temp_c)}</td>
            <td>{fmt(month.rh_pct, 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
