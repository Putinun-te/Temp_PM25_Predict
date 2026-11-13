import { describe, expect, it } from "vitest";
import { bandFor } from "./aqi";
import { accuracyTable, recentScored } from "./accuracy";
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
