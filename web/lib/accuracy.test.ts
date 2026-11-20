import { describe, expect, it } from "vitest";
import { chanceTable } from "./accuracy";
import type { AccuracySummary } from "./types";

const row = { source: "forecast" as const, n: 10, mae: 1, persistence_mae: 2, skill_vs_persistence: 0.5, coverage: 0.8 };
const extra = { n: 100, days: 10, mae: 1, mape_pct: 5, paired_mae: 1, persistence_mae: 2, coverage: 0.8 };

describe("chanceTable", () => {
  it("keeps only scored chances, city before stations, by horizon", () => {
    const summary: AccuracySummary = {
      generated_at: "now",
      latest_scored: "2026-11-20",
      windows: [7, 30, 90],
      alerts: [],
      rows: [
        { ...row, target: "pm25", label: "tomorrow", window_days: 30, chance_n: 9, chance_events: 1, brier: 0.05, base_rate_brier: 0.09 },
        { ...row, target: "pm25", label: "today", window_days: 30, chance_n: 10, chance_events: 2, brier: 0.04, base_rate_brier: 0.16 },
        { ...row, target: "pm25", label: "today", window_days: 7, chance_n: 7, brier: 0.1, base_rate_brier: 0.1 },
        { ...row, target: "temp_c", label: "today", window_days: 30 },
        { ...row, source: "tmd", target: "pm25", label: "today", window_days: 30, chance_n: 3 },
      ],
      stations: [{ ...extra, label: "today", window_days: 30, chance_n: 200, chance_events: 12, brier: 0.06, base_rate_brier: 0.05 }],
      stations_pm10: [{ ...extra, label: "today", window_days: 30 }],
    };
    const table = chanceTable(summary, 30);
    expect(table.map((r) => `${r.kind}:${r.label}`)).toEqual(["city_pm25:today", "city_pm25:tomorrow", "stations:today"]);
    expect(table[2]?.chance_events).toBe(12);
  });
});
