import type { AccuracyRow, AccuracySummary, ChanceScore, ScoredForecast } from "./types";

const TARGET_ORDER = ["pm25", "pm10", "temp_c", "rh_pct"];
const LABEL_ORDER = ["today", "tomorrow", "day2", "day3", "day4", "day5", "day6"];

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

export type ChanceKind = "city_pm25" | "city_pm10" | "stations" | "stations_pm10";

export interface ChanceRow extends ChanceScore {
  kind: ChanceKind;
  label: string;
  threshold: number;
  chance_n: number;
}

const STANDARD: Record<ChanceKind, number> = { city_pm25: 37.5, stations: 37.5, city_pm10: 120, stations_pm10: 120 };

/** Live scores of the chance above the standard for one window: city first, then stations, by horizon. */
export function chanceTable(summary: AccuracySummary, windowDays: number): ChanceRow[] {
  const city = summary.rows
    .filter((row) => row.source === "forecast" && (row.target === "pm25" || row.target === "pm10"))
    .map((row) => ({ ...row, kind: `city_${row.target}` as ChanceKind }));
  const stations = (["stations", "stations_pm10"] as const).flatMap((kind) =>
    (summary[kind] ?? []).map((row) => ({ ...row, kind })),
  );
  const kinds: ChanceKind[] = ["city_pm25", "city_pm10", "stations", "stations_pm10"];
  return [...city, ...stations]
    .filter((row) => row.window_days === windowDays)
    .flatMap((row) => {
      // Summaries from before band edges were scored hold only the standard.
      const scores = row.chances ?? [{ threshold: STANDARD[row.kind], ...row }];
      return scores.map((score) => ({
        kind: row.kind,
        label: row.label,
        threshold: score.threshold,
        chance_n: score.chance_n ?? 0,
        chance_events: score.chance_events,
        brier: score.brier,
        base_rate_brier: score.base_rate_brier,
      }));
    })
    .filter((row) => row.chance_n > 0)
    .sort(
      (a, b) =>
        kinds.indexOf(a.kind) - kinds.indexOf(b.kind) ||
        LABEL_ORDER.indexOf(a.label) - LABEL_ORDER.indexOf(b.label) ||
        a.threshold - b.threshold,
    );
}

/** Newest scored forecasts for one target and horizon from our own model, newest first. */
export function recentScored(rows: ScoredForecast[], target: string, label: string, count: number): ScoredForecast[] {
  return rows
    .filter((row) => row.target === target && row.label === label && row.source === "forecast")
    .sort((a, b) => b.period.localeCompare(a.period))
    .slice(0, count);
}

/** Share of the measured value the forecast got right: 100 minus the error percent, never below 0. */
export function matchPercent(errorPercent: number | null | undefined): number | null {
  if (errorPercent === null || errorPercent === undefined || Number.isNaN(errorPercent)) return null;
  return Math.max(0, 100 - errorPercent);
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

/** Our forecasts for one target on its newest measured days, newest first. */
export function recentDayChecks(rows: ScoredForecast[], target: string, days: number): DayCheck[] {
  const mine = rows.filter((row) => row.source === "forecast" && row.target === target && row.actual !== null);
  const dates = [...new Set(mine.map((row) => row.period))].sort().reverse().slice(0, days);
  return dates.map((date) => {
    const day = mine.filter((row) => row.period === date);
    const actual = day.find((row) => row.actual !== null)?.actual ?? 0;
    return {
      target,
      date,
      actual,
      sameDay: check(day.find((row) => row.label === "today"), actual),
      dayBefore: check(day.find((row) => row.label === "tomorrow"), actual),
    };
  });
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
