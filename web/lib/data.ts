import type { AccuracySummary, DailyRow, Forecast, HistoryRow, Point, ScoredForecast, StationsFile } from "./types";

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

/** Parse the simple CSV files written by the pipeline (no quoted commas). */
export function parseCsv(text: string): Record<string, string>[] {
  const [header, ...lines] = text.trim().split(/\r?\n/);
  if (!header) return [];
  const keys = header.split(",");
  return lines
    .filter((line) => line.length > 0)
    .map((line) => {
      const values = line.split(",");
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
