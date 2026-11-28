// OpenAPI 3.1 description of the API, served at /api/openapi.json.
// Schemas are JSON Schema 2020-12, so the tests validate real responses with them.
// Objects allow extra fields: the pipeline may add a field without breaking clients.

import { LABELS, MAX_DAYS, TARGETS } from "./query.js";

/** Endpoint overview for /api/help; every path here must be in SPEC.paths. */
export const ENDPOINTS = {
  "/api/openapi.json": "OpenAPI 3.1 description of every endpoint and response",
  "/api/forecast": "Latest forecast: the next seven days (labels today, tomorrow, day2 to day6), the next three months, and each station for the same seven days (station_forecasts, with PM10 where measured)",
  "/api/measured?target=pm25&from=YYYY-MM-DD&to=YYYY-MM-DD": "Measured Bangkok daily values (pm25, pm10, temp_c, rh_pct)",
  "/api/forecasts?target=pm25&label=tomorrow&from=YYYY-MM-DD&to=YYYY-MM-DD": "Every published daily forecast in the range",
  "/api/hourly": "Hourly PM2.5 and PM10 forecast to 23:00 tomorrow, Bangkok time; updated after midday (see inputs_through)",
  "/api/accuracy": "Live accuracy of published forecasts over 7, 30 and 90 days",
  "/api/stations": "Daily values per reference station for the last 14 days",
};

const number = { type: "number" } as const;
const integer = { type: "integer" } as const;
const string = { type: "string" } as const;
const maybeNumber = { type: ["number", "null"] } as const;
const date = { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$" } as const;
const ref = (name: string) => ({ $ref: `#/components/schemas/${name}` });

/** Value, range and method of every target, as named in forecast.json rows. */
function targetFields(targets: readonly string[]) {
  const fields: Record<string, unknown> = {};
  for (const target of targets) {
    fields[target] = { ...maybeNumber, description: "Forecast value" };
    fields[`${target}_low`] = { ...maybeNumber, description: "Low end of the 80 % range" };
    fields[`${target}_high`] = { ...maybeNumber, description: "High end of the 80 % range" };
    fields[`${target}_method`] = { ...string, description: "Method that made the forecast" };
  }
  return fields;
}

const chances = {
  type: ["array", "null"],
  description: "Chance that the value is above each threshold",
  items: { type: "object", required: ["threshold", "p"], properties: { threshold: number, p: { type: ["number", "null"], minimum: 0, maximum: 1 } } },
};

const errorResponse = (description: string) => ({
  description,
  content: { "application/json": { schema: ref("Error") } },
});

const ok = (schema: string, description: string) => ({
  200: { description, content: { "application/json": { schema: ref(schema) } } },
  502: errorResponse("The data source is unavailable; try again later"),
  500: errorResponse("Internal error"),
});

const rangeParameters = [
  { name: "target", in: "query", schema: { type: "string", enum: TARGETS, default: "pm25" } },
  { name: "from", in: "query", description: "First date, YYYY-MM-DD. Default: 29 days before `to`.", schema: date },
  { name: "to", in: "query", description: "Last date, YYYY-MM-DD. Default: the newest date with data.", schema: date },
];

export const SPEC = {
  openapi: "3.1.0",
  info: {
    title: "Bangkok PM2.5 forecast API",
    version: "1.0.0",
    description:
      "Read-only, public API over the forecast data branch. Times are Bangkok time. " +
      `Ranges default to the last 30 days and can cover at most ${MAX_DAYS} days. ` +
      "Responses may hold more fields than listed here.",
  },
  servers: [{ url: "/" }],
  paths: {
    "/api/help": { get: { summary: "List of endpoints", responses: ok("Help", "Endpoint list") } },
    "/api/openapi.json": { get: { summary: "This description", responses: { 200: { description: "OpenAPI document" } } } },
    "/api/forecast": {
      get: {
        summary: "Latest forecast",
        description: "The next seven days, the next three months, and each station for the same seven days.",
        responses: ok("Forecast", "Latest forecast"),
      },
    },
    "/api/measured": {
      get: {
        summary: "Measured Bangkok daily values",
        parameters: rangeParameters,
        responses: { ...ok("Measured", "Daily values; a day without data has value null"), 400: errorResponse("A bad parameter") },
      },
    },
    "/api/forecasts": {
      get: {
        summary: "Every published daily forecast in a range of target dates",
        parameters: [...rangeParameters, { name: "label", in: "query", description: "One horizon only", schema: { type: "string", enum: LABELS } }],
        responses: { ...ok("Forecasts", "Published forecasts"), 400: errorResponse("A bad parameter") },
      },
    },
    "/api/hourly": { get: { summary: "Hourly PM2.5 and PM10 forecast to 23:00 tomorrow", responses: ok("Hourly", "Hourly forecast") } },
    "/api/accuracy": { get: { summary: "Live accuracy over 7, 30 and 90 days", responses: ok("Accuracy", "Live accuracy") } },
    "/api/stations": { get: { summary: "Daily values per reference station, last 14 days", responses: ok("Stations", "Station values") } },
  },
  components: {
    schemas: {
      Error: { type: "object", required: ["error"], properties: { error: string } },
      Help: {
        type: "object",
        required: ["name", "endpoints"],
        properties: { name: string, source: string, note: string, endpoints: { type: "object", additionalProperties: string } },
      },
      DailyForecast: {
        type: "object",
        required: ["date", "label", "horizon_days"],
        properties: {
          date,
          label: { type: "string", enum: LABELS },
          horizon_days: { ...integer, minimum: 1 },
          ...targetFields(TARGETS),
          pm25_p_above_standard: maybeNumber,
          pm25_p_above: chances,
          pm10_p_above_standard: maybeNumber,
          pm10_p_above: chances,
          temp_c_model: { ...maybeNumber, description: "Model forecast before the bias correction" },
          temp_c_bias: { ...maybeNumber, description: "Half the mean error of the last 30 scored days, added to the model forecast" },
          tmd_temp_c: { ...number, description: "Thai Meteorological Department forecast, for reference" },
          tmd_temp_c_min: number,
          tmd_temp_c_max: number,
          tmd_rh_pct: number,
        },
      },
      MonthlyForecast: {
        type: "object",
        required: ["month", "months_ahead"],
        properties: { month: { type: "string", pattern: "^\\d{4}-\\d{2}$" }, months_ahead: { ...integer, minimum: 1 }, ...targetFields(TARGETS) },
      },
      StationDay: {
        type: "object",
        required: ["pm25"],
        properties: {
          pm25: maybeNumber,
          low: maybeNumber,
          high: maybeNumber,
          method: string,
          p_above_standard: maybeNumber,
          p_above: chances,
          pm10: { ...ref("StationPm10"), description: "Only at stations that measure PM10" },
        },
      },
      StationPm10: {
        type: "object",
        required: ["pm10"],
        properties: { pm10: maybeNumber, low: maybeNumber, high: maybeNumber, method: string, p_above_standard: maybeNumber, p_above: chances },
      },
      Forecast: {
        type: "object",
        required: ["as_of", "latest_data_date", "daily", "monthly", "station_forecasts"],
        properties: {
          schema_version: integer,
          generated_at: string,
          as_of: date,
          latest_data_date: date,
          data_age_days: integer,
          status: string,
          units: { type: "object", additionalProperties: string },
          daily: { type: "array", items: ref("DailyForecast") },
          monthly: { type: "array", items: ref("MonthlyForecast") },
          gistda: { type: "object", properties: { source: string, observed_at: string, pm25_hourly: maybeNumber, pm25_24h_mean: maybeNumber } },
          station_forecasts: {
            type: "array",
            items: {
              type: "object",
              required: ["location_id"],
              properties: { location_id: integer, ...Object.fromEntries(LABELS.map((label) => [label, ref("StationDay")])) },
            },
          },
        },
      },
      Measured: {
        type: "object",
        required: ["target", "from", "to", "values"],
        properties: {
          target: { type: "string", enum: TARGETS },
          from: date,
          to: date,
          values: { type: "array", items: { type: "object", required: ["date", "value"], properties: { date, value: maybeNumber } } },
        },
      },
      Forecasts: {
        type: "object",
        required: ["target", "label", "from", "to", "forecasts"],
        properties: {
          target: { type: "string", enum: TARGETS },
          label: { type: ["string", "null"], enum: [...LABELS, null] },
          from: date,
          to: date,
          forecasts: {
            type: "array",
            items: {
              type: "object",
              required: ["issued", "date", "label", "value", "low", "high", "method"],
              properties: { issued: date, date, label: { type: "string", enum: LABELS }, value: maybeNumber, low: maybeNumber, high: maybeNumber, method: string },
            },
          },
        },
      },
      Hourly: {
        type: "object",
        required: ["as_of", "inputs_through", "hours"],
        properties: {
          generated_at: string,
          as_of: date,
          timezone: string,
          unit: string,
          method: string,
          pm10_method: string,
          inputs_through: { type: "string", description: "Newest measured hour the forecast uses" },
          measured: { type: "array", items: { type: "object", required: ["time"], properties: { time: string, pm25: maybeNumber, pm10: maybeNumber } } },
          hours: {
            type: "array",
            items: {
              type: "object",
              required: ["time", "pm25"],
              properties: {
                time: string,
                day: string,
                pm25: maybeNumber,
                low: maybeNumber,
                high: maybeNumber,
                p_above: chances,
                pm10: maybeNumber,
                pm10_low: maybeNumber,
                pm10_high: maybeNumber,
                pm10_p_above: chances,
              },
            },
          },
        },
      },
      Accuracy: {
        type: "object",
        required: ["latest_scored", "rows", "alerts"],
        properties: {
          generated_at: string,
          latest_scored: { type: ["string", "null"] },
          windows: { type: "array", items: integer },
          rows: {
            type: "array",
            items: {
              type: "object",
              required: ["target", "label", "window_days", "n"],
              properties: {
                target: { type: "string", enum: TARGETS },
                label: string,
                source: string,
                window_days: integer,
                n: integer,
                mae: maybeNumber,
                persistence_mae: maybeNumber,
                skill_vs_persistence: maybeNumber,
                coverage: maybeNumber,
              },
            },
          },
          alerts: { type: "array", items: string },
        },
      },
      Stations: {
        type: "object",
        required: ["dates", "stations"],
        properties: {
          generated_at: string,
          dates: { type: "array", items: date },
          stations: {
            type: "array",
            items: {
              type: "object",
              required: ["location_id", "name", "latitude", "longitude"],
              properties: { location_id: integer, name: string, locality: { type: ["string", "null"] }, latitude: number, longitude: number },
            },
          },
        },
      },
    },
  },
};
