import { describe, expect, it } from "vitest";
import { BadRequest, dateRange, forecasts, latestDate, measured, parseCsv, pickLabel, pickTarget } from "./query";
import { clearCache, fetchText, UpstreamError } from "./source";

const SILVER = parseCsv("date,pm25,pm10,temp_c,rh_pct\n2026-11-10,13.9,24.8,29.3,59.2\n2026-11-11,10.8,,27.2,58.8\n2026-11-12,,,27.6,64.5\n");
const HISTORY = parseCsv(
  "as_of,generated_at,kind,period,label,target,value,low,high,method,unit\n" +
    "2026-11-11,x,daily,2026-11-11,today,pm25,16.3,11.2,21.4,gradient_boosting,ug/m3\n" +
    "2026-11-11,x,daily,2026-11-12,tomorrow,pm25,21.2,13.9,28.5,random_forest,ug/m3\n" +
    "2026-11-11,x,daily,2026-11-12,tomorrow,pm10,34.6,23.7,45.4,random_forest,ug/m3\n" +
    "2026-11-11,x,monthly,2026-12,1,pm25,30.0,25.0,35.0,climatology,ug/m3\n",
);
const q = (text: string) => new URLSearchParams(text);

describe("parameters", () => {
  it("defaults to pm25 and accepts known targets only", () => {
    expect(pickTarget(q(""))).toBe("pm25");
    expect(pickTarget(q("target=rh_pct"))).toBe("rh_pct");
    expect(() => pickTarget(q("target=co2"))).toThrow(BadRequest);
    expect(pickLabel(q(""))).toBeNull();
    expect(() => pickLabel(q("label=next_week"))).toThrow(BadRequest);
  });

  it("defaults to the last 30 days and refuses bad or long ranges", () => {
    expect(dateRange(q(""), "2026-11-12")).toEqual({ from: "2026-10-14", to: "2026-11-12" });
    expect(dateRange(q("from=2026-11-01&to=2026-11-05"), "x")).toEqual({ from: "2026-11-01", to: "2026-11-05" });
    expect(() => dateRange(q("from=2026-13-40"), "2026-11-12")).toThrow(BadRequest);
    expect(() => dateRange(q("from=2026-02-30"), "2026-11-12")).toThrow(BadRequest);
    expect(dateRange(q("from=2024-02-29&to=2024-03-01"), "x")).toEqual({ from: "2024-02-29", to: "2024-03-01" });
    expect(() => dateRange(q("from=2026-11-05&to=2026-11-01"), "x")).toThrow("from must not be after to");
    expect(() => dateRange(q("from=2024-01-01&to=2026-01-01"), "x")).toThrow("at most 400 days");
  });
});

describe("filters", () => {
  it("returns measured values with gaps as null", () => {
    expect(latestDate(SILVER, "pm25")).toBe("2026-11-11");
    expect(measured(SILVER, "pm25", { from: "2026-11-11", to: "2026-11-12" })).toEqual([
      { date: "2026-11-11", value: 10.8 },
      { date: "2026-11-12", value: null },
    ]);
  });

  it("returns daily forecasts only, optionally for one horizon", () => {
    const all = forecasts(HISTORY, "pm25", null, { from: "2026-11-01", to: "2026-11-30" });
    expect(all.map((f) => f.label)).toEqual(["today", "tomorrow"]);
    expect(forecasts(HISTORY, "pm25", "tomorrow", { from: "2026-11-12", to: "2026-11-12" })).toEqual([
      { issued: "2026-11-11", date: "2026-11-12", label: "tomorrow", value: 21.2, low: 13.9, high: 28.5, method: "random_forest" },
    ]);
  });
});

describe("fetchText", () => {
  it("caches, and serves the stale copy when the source fails", async () => {
    clearCache();
    let calls = 0;
    const ok = (async () => {
      calls += 1;
      return new Response("hello");
    }) as typeof fetch;
    const down = (async () => new Response("", { status: 503 })) as typeof fetch;

    expect(await fetchText("a", ok, 0)).toBe("hello");
    expect(await fetchText("a", ok, 1000)).toBe("hello");
    expect(calls).toBe(1);
    expect(await fetchText("a", down, 60 * 60 * 1000)).toBe("hello");
    await expect(fetchText("b", down, 0)).rejects.toThrow(UpstreamError);
  });
});
