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

export interface Check {
  forecast: number;
  /** forecast minus measured: positive means the forecast was too high. */
  diff: number;
  /** Absolute error as a share of the measured value, in percent. Null when measured is 0. */
  percent: number | null;
}

export interface DayCheck {
  target: string;
  date: string;
  actual: number;
  sameDay: Check | null; // Issued on the morning of the day itself
  dayBefore: Check | null; // Issued one day earlier
}

function check(row: ScoredForecast | undefined, actual: number): Check | null {
  if (!row || row.forecast === null) return null;
  const diff = row.forecast - actual;
  return { forecast: row.forecast, diff, percent: actual === 0 ? null : (Math.abs(diff) / actual) * 100 };
}

/** Our forecasts for the newest measured day, next to what was measured. */
export function latestDayChecks(rows: ScoredForecast[]): DayCheck[] {
  const ours = rows.filter((row) => row.source === "forecast" && row.actual !== null);
  const date = ours.reduce((max, row) => (row.period > max ? row.period : max), "");
  const day = ours.filter((row) => row.period === date);
  return TARGET_ORDER.flatMap((target) => {
    const mine = day.filter((row) => row.target === target);
    const actual = mine[0]?.actual;
    if (actual === null || actual === undefined) return [];
    return [
      {
        target,
        date,
        actual,
        sameDay: check(mine.find((row) => row.label === "today"), actual),
        dayBefore: check(mine.find((row) => row.label === "tomorrow"), actual),
      },
    ];
  });
}
