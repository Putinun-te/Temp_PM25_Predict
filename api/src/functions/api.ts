import { app, type HttpRequest, type HttpResponseInit } from "@azure/functions";
import {
  BadRequest,
  dateRange,
  forecasts,
  latestDate,
  measured,
  parseCsv,
  pickLabel,
  pickTarget,
} from "../lib/query.js";
import { fetchText, UpstreamError } from "../lib/source.js";

const HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  // Public, read-only data: any site may call it, and browsers may cache it briefly.
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "public, max-age=600",
};

function json(body: unknown, status = 200): HttpResponseInit {
  return { status, headers: HEADERS, body: JSON.stringify(body) };
}

/** Turn known errors into 400 or 502; anything else is a 500 without internal details. */
function handler(run: (request: HttpRequest) => Promise<unknown>) {
  return async (request: HttpRequest): Promise<HttpResponseInit> => {
    try {
      return json(await run(request));
    } catch (error) {
      if (error instanceof BadRequest) return json({ error: error.message }, 400);
      if (error instanceof UpstreamError) return json({ error: "data source unavailable, try again later" }, 502);
      return json({ error: "internal error" }, 500);
    }
  };
}

function params(request: HttpRequest): URLSearchParams {
  return new URL(request.url).searchParams;
}

const ENDPOINTS = {
  "/api/forecast": "Latest forecast: today, tomorrow and the next three months",
  "/api/measured?target=pm25&from=YYYY-MM-DD&to=YYYY-MM-DD": "Measured Bangkok daily values (pm25, pm10, temp_c, rh_pct)",
  "/api/forecasts?target=pm25&label=tomorrow&from=YYYY-MM-DD&to=YYYY-MM-DD": "Every published daily forecast in the range",
  "/api/accuracy": "Live accuracy of published forecasts over 7, 30 and 90 days",
  "/api/stations": "Daily values per reference station for the last 14 days",
};

// Azure Functions does not allow an empty route, so the overview lives at /api/help.
app.http("help", {
  methods: ["GET"],
  authLevel: "anonymous",
  handler: handler(async () => ({
    name: "Bangkok PM2.5 forecast API",
    source: "https://github.com/Putinun-te/Temp_PM25_Predict",
    note: "Ranges default to the last 30 days and can cover at most 400 days.",
    endpoints: ENDPOINTS,
  })),
});

app.http("forecast", {
  methods: ["GET"],
  authLevel: "anonymous",
  handler: handler(async () => JSON.parse(await fetchText("data/gold/forecast.json"))),
});

app.http("measured", {
  methods: ["GET"],
  authLevel: "anonymous",
  handler: handler(async (request) => {
    const query = params(request);
    const target = pickTarget(query);
    const rows = parseCsv(await fetchText("data/silver/daily_city.csv"));
    const range = dateRange(query, latestDate(rows, target));
    return { target, ...range, values: measured(rows, target, range) };
  }),
});

app.http("forecasts", {
  methods: ["GET"],
  authLevel: "anonymous",
  handler: handler(async (request) => {
    const query = params(request);
    const target = pickTarget(query);
    const label = pickLabel(query);
    const rows = parseCsv(await fetchText("data/gold/forecast_history.csv"));
    const newest = rows.reduce((max, row) => ((row.period ?? "") > max && /^\d{4}-\d{2}-\d{2}$/.test(row.period ?? "") ? row.period! : max), "");
    const range = dateRange(query, newest);
    return { target, label, ...range, forecasts: forecasts(rows, target, label, range) };
  }),
});

app.http("accuracy", {
  methods: ["GET"],
  authLevel: "anonymous",
  handler: handler(async () => JSON.parse(await fetchText("data/gold/live_accuracy_summary.json"))),
});

app.http("stations", {
  methods: ["GET"],
  authLevel: "anonymous",
  handler: handler(async () => JSON.parse(await fetchText("data/gold/stations.json"))),
});
