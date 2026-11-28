import { Ajv2020 } from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";
import { ENDPOINTS, SPEC } from "./openapi";
import { forecasts, measured, parseCsv } from "./query";
import { DATA_BASE } from "./source";

const ajv = new Ajv2020({ strict: false, allErrors: true });
ajv.addSchema(SPEC, "spec");

function errors(schema: string, body: unknown): string[] {
  const validate = ajv.getSchema(`spec#/components/schemas/${schema}`)!;
  return validate(body) ? [] : (validate.errors ?? []).slice(0, 5).map((e) => `${e.instancePath} ${e.message}`);
}

describe("OpenAPI description", () => {
  it("describes every endpoint the help lists, and no others", () => {
    const listed = Object.keys(ENDPOINTS).map((path) => path.split("?")[0]).concat("/api/help").sort();
    expect(Object.keys(SPEC.paths).sort()).toEqual(listed);
  });

  it("accepts what the range endpoints return", () => {
    const silver = parseCsv("date,pm25\n2026-11-10,13.9\n2026-11-11,\n");
    const range = { from: "2026-11-10", to: "2026-11-11" };
    expect(errors("Measured", { target: "pm25", ...range, values: measured(silver, "pm25", range) })).toEqual([]);
    const history = parseCsv(
      "as_of,kind,period,label,target,value,low,high,method\n2026-11-10,daily,2026-11-11,tomorrow,pm25,21.2,,28.5,random_forest\n",
    );
    const body = { target: "pm25", label: null, ...range, forecasts: forecasts(history, "pm25", null, range) };
    expect(errors("Forecasts", body)).toEqual([]);
  });

  it("refuses a forecast row that breaks the contract", () => {
    const day = { date: "2026-11-28", label: "today", horizon_days: 1, temp_c: 30.2, temp_c_bias: 0.16 };
    const forecast = { as_of: "2026-11-28", latest_data_date: "2026-11-27", daily: [day], monthly: [], station_forecasts: [] };
    expect(errors("Forecast", forecast)).toEqual([]);
    expect(errors("Forecast", { ...forecast, daily: [{ ...day, label: "next week" }] })).not.toEqual([]);
    expect(errors("Forecast", { ...forecast, daily: [{ ...day, temp_c: "30" }] })).not.toEqual([]);
  });
});

// The published data, checked against the description. Needs the network: `npm run check:live`.
const FILES = [
  ["Forecast", "data/gold/forecast.json"],
  ["Hourly", "data/gold/hourly_forecast.json"],
  ["Accuracy", "data/gold/live_accuracy_summary.json"],
  ["Stations", "data/gold/stations.json"],
] as const;

describe.runIf(process.env.CHECK_LIVE === "1")("published data", () => {
  it.each(FILES)("%s matches %s", async (schema, path) => {
    const response = await fetch(`${DATA_BASE}/${path}`);
    expect(response.ok).toBe(true);
    expect(errors(schema, await response.json())).toEqual([]);
  });
});
