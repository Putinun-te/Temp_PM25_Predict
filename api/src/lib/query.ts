// Pure request handling: parameter checks and filtering. No network, so it is unit tested.

export const TARGETS = ["pm25", "pm10", "temp_c", "rh_pct"] as const;
export const LABELS = ["today", "tomorrow"] as const;
export const MAX_DAYS = 400;

export type Target = (typeof TARGETS)[number];
export type Row = Record<string, string>;

export class BadRequest extends Error {}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Parse the pipeline's simple CSV files (no quoted commas). */
export function parseCsv(text: string): Row[] {
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

export function toNumber(value: string | undefined): number | null {
  if (value === undefined || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function isoDate(value: string, name: string): string {
  // Date.parse rolls 2026-02-30 over to 1 March, so the date must survive a round trip.
  const parsed = DATE.test(value) ? new Date(`${value}T00:00:00Z`) : null;
  if (!parsed || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new BadRequest(`${name} must be a date as YYYY-MM-DD`);
  }
  return value;
}

function addDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export interface Range {
  from: string;
  to: string;
}

/**
 * Read `from` and `to`. Without them the range is the last 30 days up to `latest`.
 * A range longer than MAX_DAYS is refused, which keeps responses small.
 */
export function dateRange(params: URLSearchParams, latest: string): Range {
  const to = params.get("to") ? isoDate(params.get("to")!, "to") : latest;
  const from = params.get("from") ? isoDate(params.get("from")!, "from") : addDays(to, -29);
  if (from > to) throw new BadRequest("from must not be after to");
  const days = (Date.parse(to) - Date.parse(from)) / 86_400_000 + 1;
  if (days > MAX_DAYS) throw new BadRequest(`a range can cover at most ${MAX_DAYS} days`);
  return { from, to };
}

export function pickTarget(params: URLSearchParams): Target {
  const value = params.get("target") ?? "pm25";
  if (!(TARGETS as readonly string[]).includes(value)) {
    throw new BadRequest(`target must be one of ${TARGETS.join(", ")}`);
  }
  return value as Target;
}

export function pickLabel(params: URLSearchParams): string | null {
  const value = params.get("label");
  if (value === null) return null;
  if (!(LABELS as readonly string[]).includes(value)) {
    throw new BadRequest(`label must be one of ${LABELS.join(", ")}`);
  }
  return value;
}

/** Measured daily values for one target, from silver/daily_city.csv. */
export function measured(rows: Row[], target: Target, range: Range) {
  return rows
    .filter((row) => (row.date ?? "") >= range.from && (row.date ?? "") <= range.to)
    .map((row) => ({ date: row.date ?? "", value: toNumber(row[target]) }));
}

/** Published daily forecasts for one target, from gold/forecast_history.csv. */
export function forecasts(rows: Row[], target: Target, label: string | null, range: Range) {
  return rows
    .filter((row) => row.kind === "daily" && row.target === target)
    .filter((row) => label === null || row.label === label)
    .filter((row) => (row.period ?? "") >= range.from && (row.period ?? "") <= range.to)
    .map((row) => ({
      issued: row.as_of ?? "",
      date: row.period ?? "",
      label: row.label ?? "",
      value: toNumber(row.value),
      low: toNumber(row.low),
      high: toNumber(row.high),
      method: row.method ?? "",
    }));
}

/** Newest date in silver that has a value for the target. */
export function latestDate(rows: Row[], target: Target): string {
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const row = rows[i]!;
    if (toNumber(row[target]) !== null) return row.date ?? "";
  }
  return rows.at(-1)?.date ?? "";
}
