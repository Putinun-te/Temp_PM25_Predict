import { describe, expect, it } from "vitest";
import { bandFor } from "./aqi";
import { accuracyTable, latestDayChecks, matchPercent, recentDayChecks, recentScored } from "./accuracy";
import { pickLang, translate } from "./i18n";
import type { AccuracySummary, ScoredForecast } from "./types";

describe("bandFor", () => {
  it("uses the PCD PM2.5 bands with the 37.5 standard", () => {
    expect(bandFor("pm25", 15)?.level).toBe(1);
    expect(bandFor("pm25", 15.1)?.level).toBe(2);
    expect(bandFor("pm25", 37.5)?.level).toBe(3);
    expect(bandFor("pm25", 37.54)?.level).toBe(3);
    expect(bandFor("pm25", 37.6)?.level).toBe(4);
    expect(bandFor("pm25", 75.1)?.level).toBe(5);
    expect(bandFor("pm25", 400)?.en).toBe("Affects health");
  });

  it("uses the PM10 bands", () => {
    expect(bandFor("pm10", 50)?.level).toBe(1);
    expect(bandFor("pm10", 81)?.level).toBe(3);
    expect(bandFor("pm10", 181)?.level).toBe(5);
  });

  it("has no band without a value", () => {
    expect(bandFor("pm25", null)).toBeNull();
    expect(bandFor("pm25", Number.NaN)).toBeNull();
  });
});

describe("pickLang", () => {
  it("prefers the query, then the saved choice, then the browser", () => {
    expect(pickLang("?lang=th", "en", "en-US")).toBe("th");
    expect(pickLang("", "th", "en-US")).toBe("th");
    expect(pickLang("?lang=xx", null, "th-TH")).toBe("th");
    expect(pickLang("", null, undefined)).toBe("en");
    expect(translate("th", "today")).toBe("วันนี้");
  });
});

describe("accuracy helpers", () => {
  const row = (target: string, label: string, source: "forecast" | "tmd", window_days: number, n = 3) => ({
    target, label, source, window_days, n, mae: 1, persistence_mae: 2, skill_vs_persistence: 0.5, coverage: 1,
  });
  const summary: AccuracySummary = {
    generated_at: "",
    latest_scored: "2026-11-12",
    windows: [7, 30],
    alerts: [],
    rows: [row("temp_c", "tomorrow", "tmd", 7), row("temp_c", "tomorrow", "forecast", 7), row("pm25", "tomorrow", "forecast", 7), row("pm25", "today", "forecast", 7, 0), row("pm25", "today", "forecast", 30)],
  };

  it("orders one window and drops empty rows", () => {
    expect(accuracyTable(summary, 7).map((r) => `${r.target}/${r.label}/${r.source}`)).toEqual([
      "pm25/tomorrow/forecast",
      "temp_c/tomorrow/forecast",
      "temp_c/tomorrow/tmd",
    ]);
  });

  it("returns the newest scored forecasts first", () => {
    const scored: ScoredForecast[] = ["2026-11-10", "2026-11-12", "2026-11-11"].map((period) => ({
      as_of: "", period, label: "tomorrow", target: "pm25", source: "forecast", forecast: 1, actual: 1, abs_error: 0,
    }));
    expect(recentScored(scored, "pm25", "tomorrow", 2).map((r) => r.period)).toEqual(["2026-11-12", "2026-11-11"]);
  });
});

describe("latestDayChecks", () => {
  const row = (period: string, label: string, target: string, forecast: number, actual: number, source = "forecast"): ScoredForecast => ({
    as_of: "", period, label, target, source, forecast, actual, abs_error: Math.abs(forecast - actual),
  });

  it("compares both forecasts for the newest measured day", () => {
    const checks = latestDayChecks([
      row("2026-11-13", "today", "pm25", 99, 10),
      row("2026-11-14", "today", "pm25", 20, 25),
      row("2026-11-14", "tomorrow", "pm25", 30, 25),
      row("2026-11-14", "today", "temp_c", 28, 29, "tmd"),
      row("2026-11-14", "today", "rh_pct", 70, 70),
    ]);
    expect(checks.map((c) => c.target)).toEqual(["pm25", "rh_pct"]);
    const pm25 = checks[0]!;
    expect(pm25.date).toBe("2026-11-14");
    expect(pm25.sameDay).toEqual({ forecast: 20, diff: -5, percent: 20 });
    expect(pm25.dayBefore).toEqual({ forecast: 30, diff: 5, percent: 20 });
    expect(checks[1]!.dayBefore).toBeNull();
  });

  it("returns nothing before any forecast is scored", () => {
    expect(latestDayChecks([])).toEqual([]);
  });
});

describe("matchPercent", () => {
  it("is 100 minus the error percent, floored at 0", () => {
    expect(matchPercent(22)).toBe(78);
    expect(matchPercent(140)).toBe(0);
    expect(matchPercent(null)).toBeNull();
  });
});

describe("hourLabel", () => {
  it("shortens a local timestamp for the chart axis", async () => {
    const { hourLabel } = await import("./data");
    expect(hourLabel("2026-11-16T04:00")).toBe("16 04:00");
  });
});

describe("recentDayChecks", () => {
  const row = (period: string, label: string, forecast: number, actual: number, target = "pm25"): ScoredForecast => ({
    as_of: "", period, label, target, source: "forecast", forecast, actual, abs_error: Math.abs(forecast - actual),
  });

  it("lists the newest measured days of one target with both forecasts", () => {
    const scored = [
      row("2026-11-14", "today", 22, 20),
      row("2026-11-15", "today", 27, 30),
      row("2026-11-15", "tomorrow", 33, 30),
      row("2026-11-16", "tomorrow", 10, 20),
      row("2026-11-16", "today", 99, 50, "pm10"),
    ];
    const days = recentDayChecks(scored, "pm25", 2);
    expect(days.map((day) => day.date)).toEqual(["2026-11-16", "2026-11-15"]);
    expect(days[0]?.sameDay).toBeNull();
    expect(days[0]?.dayBefore?.percent).toBe(50);
    expect(days[1]?.sameDay?.diff).toBe(-3);
    expect(days[1]?.dayBefore?.diff).toBe(3);
  });
});
