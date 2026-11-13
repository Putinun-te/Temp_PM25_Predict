import type { AccuracyRow, AccuracySummary, ScoredForecast } from "./types";

const TARGET_ORDER = ["pm25", "pm10", "temp_c", "rh_pct"];
const LABEL_ORDER = ["today", "tomorrow"];

/** Rows for one window, PM first, our forecast before TMD, and only rows with scores. */
export function accuracyTable(summary: AccuracySummary, windowDays: number): AccuracyRow[] {
  return summary.rows
    .filter((row) => row.window_days === windowDays && row.n > 0)
    .sort(
      (a, b) =>
        TARGET_ORDER.indexOf(a.target) - TARGET_ORDER.indexOf(b.target) ||
        LABEL_ORDER.indexOf(a.label) - LABEL_ORDER.indexOf(b.label) ||
        (a.source === b.source ? 0 : a.source === "forecast" ? -1 : 1),
    );
}

/** Newest scored forecasts for one target and horizon from our own model, newest first. */
export function recentScored(rows: ScoredForecast[], target: string, label: string, count: number): ScoredForecast[] {
  return rows
    .filter((row) => row.target === target && row.label === label && row.source === "forecast")
    .sort((a, b) => b.period.localeCompare(a.period))
    .slice(0, count);
}
