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
  station_forecasts?: StationForecast[];
}

export interface StationValue {
  pm25: number | null;
  low: number | null;
  high: number | null;
  method: string;
  /** Only the stations that measure PM10 have this. */
  pm10?: { pm10: number | null; low: number | null; high: number | null; method: string };
}

export interface StationForecast {
  location_id: number;
  today?: StationValue;
  tomorrow?: StationValue;
}

export interface HourlyPoint {
  time: string; // Bangkok local time, YYYY-MM-DDTHH:MM
  day: "today" | "tomorrow";
  pm25: number | null;
  low: number | null;
  high: number | null;
}

export interface HourlyForecast {
  generated_at: string;
  as_of: string;
  method: string;
  inputs_through: string;
  measured: { time: string; pm25: number }[];
  hours: HourlyPoint[];
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
  mape_pct?: number | null;
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
  /** Hourly city forecasts and per-station daily forecasts, PM2.5 only. Absent until first scored. */
  hourly?: ExtraAccuracyRow[];
  hourly_afternoon?: ExtraAccuracyRow[];
  stations?: ExtraAccuracyRow[];
  stations_pm10?: ExtraAccuracyRow[];
}

export interface ExtraAccuracyRow {
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
