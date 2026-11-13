// Mirrors the forecast document written by the Python pipeline (schema_version 2).
// If the pipeline changes a field name, the type check fails at build time.

export type Method = string;

export interface DailyForecast {
  date: string;
  label: "today" | "tomorrow";
  horizon_days: number;
  pm25: number | null;
  pm25_low: number | null;
  pm25_high: number | null;
  pm25_method: Method;
  pm10: number | null;
  pm10_low: number | null;
  pm10_high: number | null;
  pm10_method: Method;
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

export interface AccuracyRow {
  target: string;
  label: string;
  source: "forecast" | "tmd";
  window_days: number;
  n: number;
  mae: number | null;
  persistence_mae: number | null;
  skill_vs_persistence: number | null;
  coverage: number | null;
}

export interface AccuracySummary {
  generated_at: string;
  latest_scored: string | null;
  windows: number[];
  rows: AccuracyRow[];
  alerts: string[];
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
