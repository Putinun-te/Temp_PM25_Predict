import { DAY_LABELS, type DayLabel, type HourlyForecast, type HourlyPoint, type HourlyTarget } from "./types";
import type {
  AccuracySummary,
  ChanceAbove,
  DailyRow,
  Forecast,
  HistoryRow,
  Point,
  ScoredForecast,
  ScoredStationForecast,
  StationsFile,
} from "./types";

export const DEFAULT_DATA_BASE =
  process.env.NEXT_PUBLIC_DATA_BASE ||
  "https://raw.githubusercontent.com/Putinun-te/Temp_PM25_Predict/data";

/** A `?data=` query parameter points the page at another copy, for local testing. */
export function dataBase(search: string): string {
  return new URLSearchParams(search).get("data") || DEFAULT_DATA_BASE;
}

export function toNumber(value: string | undefined): number | null {
  if (value === undefined || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/** Split one CSV line. A field in double quotes may hold commas, and "" inside it is one quote. */
export function splitCsvLine(line: string): string[] {
  const values: string[] = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (quoted) {
      if (char === '"' && line[i + 1] === '"') {
        value += '"';
        i++;
      } else if (char === '"') {
        quoted = false;
      } else {
        value += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      values.push(value);
      value = "";
    } else {
      value += char;
    }
  }
  values.push(value);
  return values;
}

/**
 * Parse the CSV files written by the pipeline. Fields may be quoted: the chance
 * columns hold JSON lists with commas. No field spans lines.
 */
export function parseCsv(text: string): Record<string, string>[] {
  const [header, ...lines] = text.trim().split(/\r?\n/);
  if (!header) return [];
  const keys = splitCsvLine(header);
  return lines
    .filter((line) => line.length > 0)
    .map((line) => {
      const values = splitCsvLine(line);
      return Object.fromEntries(keys.map((key, i) => [key, values[i] ?? ""]));
    });
}

export function toDailyRows(records: Record<string, string>[]): DailyRow[] {
  return records.map((row) => ({ date: row.date ?? "", pm25: toNumber(row.pm25) }));
}

export function toHistoryRows(records: Record<string, string>[]): HistoryRow[] {
  return records.map((row) => ({
    kind: row.kind ?? "",
    period: row.period ?? "",
    label: row.label ?? "",
    target: row.target ?? "",
    value: toNumber(row.value),
  }));
}

/** Measured PM2.5 for the most recent days that have a value. */
export function measuredSeries(rows: DailyRow[], days = 60): Point[] {
  return rows
    .filter((row): row is DailyRow & { pm25: number } => row.pm25 !== null)
    .slice(-days)
    .map((row) => ({ x: row.date, y: row.pm25 }));
}

/** PM2.5 forecasts issued the day before each date, limited to the measured window. */
export function dayBeforeForecasts(history: HistoryRow[], measured: Point[]): Point[] {
  const first = measured[0]?.x;
  return history
    .filter((row) => row.kind === "daily" && row.label === "tomorrow" && row.target === "pm25")
    .filter((row): row is HistoryRow & { value: number } => row.value !== null)
    .filter((row) => first === undefined || row.period >= first)
    .map((row) => ({ x: row.period, y: row.value }));
}

async function fetchText(base: string, path: string): Promise<string> {
  const response = await fetch(`${base}/${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.text();
}

export async function loadForecast(base: string): Promise<Forecast> {
  return JSON.parse(await fetchText(base, "data/gold/forecast.json")) as Forecast;
}

export async function loadHistory(base: string): Promise<{ daily: DailyRow[]; history: HistoryRow[] }> {
  const [daily, history] = await Promise.all([
    fetchText(base, "data/silver/daily_city.csv").then(parseCsv).then(toDailyRows),
    fetchText(base, "data/gold/forecast_history.csv")
      .then(parseCsv)
      .then(toHistoryRows)
      .catch(() => [] as HistoryRow[]),
  ]);
  return { daily, history };
}

export function toScoredRows(records: Record<string, string>[]): ScoredForecast[] {
  return records.map((row) => ({
    as_of: row.as_of ?? "",
    period: row.period ?? "",
    label: row.label ?? "",
    target: row.target ?? "",
    source: row.source ?? "",
    forecast: toNumber(row.forecast),
    actual: toNumber(row.actual),
    abs_error: toNumber(row.abs_error),
  }));
}

/** Newest station value for each station, from the last date column. */
export function latestStationValue(values: (number | null)[] | undefined): number | null {
  return values?.at(-1) ?? null;
}

/** Files written by newer pipeline steps may not exist yet, so a 404 means "none". */
async function fetchOptional<T>(base: string, path: string, parse: (text: string) => T): Promise<T | null> {
  try {
    return parse(await fetchText(base, path));
  } catch {
    return null;
  }
}

export function loadStations(base: string): Promise<StationsFile | null> {
  return fetchOptional(base, "data/gold/stations.json", (text) => JSON.parse(text) as StationsFile);
}

export async function loadAccuracy(
  base: string,
): Promise<{ summary: AccuracySummary | null; scored: ScoredForecast[] }> {
  const [summary, scored] = await Promise.all([
    fetchOptional(base, "data/gold/live_accuracy_summary.json", (text) => JSON.parse(text) as AccuracySummary),
    fetchOptional(base, "data/gold/live_accuracy.csv", (text) => toScoredRows(parseCsv(text))),
  ]);
  return { summary, scored: scored ?? [] };
}

export function loadHourly(base: string): Promise<HourlyForecast | null> {
  return fetchOptional(base, "data/gold/hourly_forecast.json", (text) => JSON.parse(text) as HourlyForecast);
}

/** "2026-11-16T04:00" becomes "16 04:00": short enough for a chart axis. */
export function hourLabel(time: string): string {
  return `${time.slice(8, 10)} ${time.slice(11, 16)}`;
}

export function toScoredStationRows(records: Record<string, string>[]): ScoredStationForecast[] {
  return records.map((row) => ({
    as_of: row.as_of ?? "",
    period: row.period ?? "",
    label: row.label ?? "",
    location_id: Number(row.location_id),
    target: row.target || "pm25",
    forecast: toNumber(row.forecast),
    actual: toNumber(row.actual),
    abs_error: toNumber(row.abs_error),
    persistence_abs_error: toNumber(row.persistence_abs_error),
    in_range: row.in_range === "True" ? true : row.in_range === "False" ? false : null,
  }));
}

export async function loadStationScores(base: string): Promise<ScoredStationForecast[]> {
  return (
    (await fetchOptional(base, "data/gold/live_accuracy_stations.csv", (text) => toScoredStationRows(parseCsv(text)))) ?? []
  );
}

/** The station id in `?id=`, or null. */
export function stationIdFrom(search: string): number | null {
  const id = Number(new URLSearchParams(search).get("id"));
  return Number.isInteger(id) && id > 0 ? id : null;
}

export interface StationSummary {
  days: number;
  mae: number | null;
  baselineMae: number | null;
  coverage: number | null;
}

/** Mean error, baseline error and range coverage of one station's scored forecasts for a target, optionally for one day ahead. */
export function summarizeStation(
  rows: ScoredStationForecast[],
  id: number,
  target: string,
  label?: string,
): StationSummary {
  const mine = rows.filter(
    (row) =>
      row.location_id === id &&
      row.target === target &&
      row.abs_error !== null &&
      (label === undefined || row.label === label),
  );
  const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);
  const ranged = mine.filter((row) => row.in_range !== null);
  return {
    days: mine.length,
    mae: mean(mine.map((row) => row.abs_error as number)),
    baselineMae: mean(mine.filter((row) => row.persistence_abs_error !== null).map((row) => row.persistence_abs_error as number)),
    coverage: ranged.length ? ranged.filter((row) => row.in_range).length / ranged.length : null,
  };
}

/**
 * The same summary for each day ahead that has scored forecasts, today first.
 * Errors grow with the days ahead, so one number for all of them would not compare fairly with the baseline.
 */
export function summarizeStationByDay(
  rows: ScoredStationForecast[],
  id: number,
  target: string,
): (StationSummary & { label: DayLabel })[] {
  return DAY_LABELS.map((label) => ({ label, ...summarizeStation(rows, id, target, label) })).filter(
    (summary) => summary.days > 0,
  );
}

/** Dates `as_of` + 0 to 6 as YYYY-MM-DD, matching the labels today to day6. */
export function forecastDates(asOf: string): string[] {
  const start = new Date(`${asOf}T00:00:00Z`);
  return Array.from({ length: 7 }, (_, i) => new Date(start.getTime() + i * 86_400_000).toISOString().slice(0, 10));
}

/** Chances to show: every tested edge when published, else the standard alone (older forecasts). */
export function chanceList(
  list: ChanceAbove[] | null | undefined,
  standardP: number | null | undefined,
  standard: number,
): ChanceAbove[] {
  if (list && list.length > 0) return [...list].sort((a, b) => a.threshold - b.threshold);
  return standardP === null || standardP === undefined ? [] : [{ threshold: standard, p: standardP }];
}

/** "23%" for 0.23; "<1%" and ">99%" at the ends, so a small chance never reads as none. */
export function chanceText(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "n/a";
  if (p < 0.01) return "<1%";
  if (p > 0.99) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** The chances of one forecast hour for the chosen target. */
export function hourChances(point: HourlyPoint, target: HourlyTarget): ChanceAbove[] {
  return chanceList(target === "pm10" ? point.pm10_p_above : point.p_above, null, 0);
}

export interface PeakChance extends ChanceAbove {
  time: string;
}

/** For each band edge, the hour with the highest chance of going above it, lowest edge first. */
export function peakChances(points: HourlyPoint[], target: HourlyTarget): PeakChance[] {
  const peaks = new Map<number, PeakChance>();
  for (const point of points) {
    for (const { threshold, p } of hourChances(point, target)) {
      const best = peaks.get(threshold);
      if (!best || p > best.p) peaks.set(threshold, { threshold, p, time: point.time });
    }
  }
  return [...peaks.values()].sort((a, b) => a.threshold - b.threshold);
}
