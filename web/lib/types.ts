/** Chance (0 to 1) that a daily mean goes above `threshold` µg/m³. */
export interface ChanceAbove {
  threshold: number;
  p: number;
}

// Mirrors the forecast document written by the Python pipeline (schema_version 2).
// If the pipeline changes a field name, the type check fails at build time.

export type Method = string;

export interface DailyForecast {
  date: string;
  label: string; // "today", "tomorrow", then "day2" to "day6": days after today
  horizon_days: number;
  pm25: number | null;
  pm25_low: number | null;
  pm25_high: number | null;
  pm25_method: Method;
  pm10: number | null;
  pm10_low: number | null;
  pm10_high: number | null;
  pm10_method: Method;
  /** Chance (0 to 1) that the daily mean goes above the Thai 24-hour standard. */
  pm25_p_above_standard?: number | null;
  pm10_p_above_standard?: number | null;
  /** Chance above each tested colour-band edge, lowest edge first. */
  pm25_p_above?: ChanceAbove[] | null;
  pm10_p_above?: ChanceAbove[] | null;
  temp_c?: number | null;
  temp_c_low?: number | null;
  temp_c_high?: number | null;
  temp_c_method?: Method;
  rh_pct?: number | null;
  rh_pct_low?: number | null;
  rh_pct_high?: number | null;
  rh_pct_method?: Method;
  tmd_temp_c?: number;
  tmd_temp_c_min?: number;
  tmd_temp_c_max?: number;
  tmd_rh_pct?: number;
}

export interface MonthlyForecast {
  month: string;
  months_ahead: number;
  pm25: number | null;
  pm25_low: number | null;
  pm25_high: number | null;
  pm25_method: Method;
  pm10: number | null;
  temp_c?: number | null;
  rh_pct?: number | null;
}

export interface GistdaReference {
  source: string;
  observed_at: string;
  pm25_hourly: number;
  pm25_24h_mean: number;
}

export interface Forecast {
  schema_version: number;
  generated_at: string;
  as_of: string;
  latest_data_date: string;
  data_age_days: number;
  status: "ok" | "stale";
  units: Record<string, string>;
  daily: DailyForecast[];
  monthly: MonthlyForecast[];
  gistda?: GistdaReference;
  station_forecasts?: StationForecast[];
}

export interface StationValue {
  pm25: number | null;
  low: number | null;
  high: number | null;
  method: string;
  /** Chance (0 to 1) that the station's daily mean goes above the Thai standard. */
  p_above_standard?: number | null;
  p_above?: ChanceAbove[] | null;
  /** Only the stations that measure PM10 have this. */
  pm10?: {
    pm10: number | null;
    low: number | null;
    high: number | null;
    method: string;
    p_above_standard?: number | null;
    p_above?: ChanceAbove[] | null;
  };
}

/** Daily labels in order: today, tomorrow, then days after today. */
export const DAY_LABELS = ["today", "tomorrow", "day2", "day3", "day4", "day5", "day6"] as const;
export type DayLabel = (typeof DAY_LABELS)[number];

export type StationForecast = { location_id: number } & Partial<Record<DayLabel, StationValue>>;

export interface HourlyPoint {
  time: string; // Bangkok local time, YYYY-MM-DDTHH:MM
  day: "today" | "tomorrow";
  pm25: number | null;
  low: number | null;
  high: number | null;
  /** PM10 is present once its hourly model exists. */
  pm10?: number | null;
  pm10_low?: number | null;
  pm10_high?: number | null;
}

export type HourlyTarget = "pm25" | "pm10";

export interface HourlyForecast {
  generated_at: string;
  as_of: string;
  method: string;
  inputs_through: string;
  measured: { time: string; pm25: number; pm10?: number }[];
  hours: HourlyPoint[];
  pm10_method?: string;
}

export interface DailyRow {
  date: string;
  pm25: number | null;
}

export interface HistoryRow {
  kind: string;
  period: string;
  label: string;
  target: string;
  value: number | null;
}

export interface Point {
  x: string;
  y: number;
}

export interface Station {
  location_id: number;
  name: string;
  locality: string;
  latitude: number;
  longitude: number;
  pm25?: (number | null)[];
  pm10?: (number | null)[];
}

export interface StationsFile {
  generated_at: string;
  dates: string[];
  stations: Station[];
}

export interface AccuracyRow extends ChanceScore {
  target: string;
  label: string;
  source: "forecast" | "tmd";
  window_days: number;
  n: number;
  mae: number | null;
  mape_pct?: number | null;
  persistence_mae: number | null;
  skill_vs_persistence: number | null;
  coverage: number | null;
}

/** Live score of the published chance above the standard; absent until a chance is scored. */
export interface ChanceScore {
  chance_n?: number;
  chance_events?: number;
  /** Mean squared error of the chance against what happened (0 is perfect). */
  brier?: number | null;
  /** The same for always saying the rate seen in the same days. */
  base_rate_brier?: number | null;
}

export interface AccuracySummary {
  generated_at: string;
  latest_scored: string | null;
  windows: number[];
  rows: AccuracyRow[];
  alerts: string[];
  /** Hourly city forecasts and per-station daily forecasts. Each section is absent until first scored. */
  hourly?: ExtraAccuracyRow[];
  hourly_afternoon?: ExtraAccuracyRow[];
  hourly_evening?: ExtraAccuracyRow[];
  hourly_pm10?: ExtraAccuracyRow[];
  hourly_pm10_afternoon?: ExtraAccuracyRow[];
  hourly_pm10_evening?: ExtraAccuracyRow[];
  stations?: ExtraAccuracyRow[];
  stations_pm10?: ExtraAccuracyRow[];
}

export interface ExtraAccuracyRow extends ChanceScore {
  label: string;
  window_days: number;
  /** Scored forecasts: hours for the hourly rows, station-days for the station rows. */
  n: number;
  days: number;
  mae: number | null;
  mape_pct: number | null;
  paired_mae: number | null;
  persistence_mae: number | null;
  coverage: number | null;
}

/** One scored station forecast from gold/live_accuracy_stations.csv. */
export interface ScoredStationForecast {
  as_of: string;
  period: string;
  label: string;
  location_id: number;
  target: string;
  forecast: number | null;
  actual: number | null;
  abs_error: number | null;
  persistence_abs_error: number | null;
  in_range: boolean | null;
}

export interface ScoredForecast {
  as_of: string;
  period: string;
  label: string;
  target: string;
  source: string;
  forecast: number | null;
  actual: number | null;
  abs_error: number | null;
}
