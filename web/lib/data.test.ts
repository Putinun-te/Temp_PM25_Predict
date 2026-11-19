import { describe, expect, it } from "vitest";
import { dataBase, dayBeforeForecasts, measuredSeries, parseCsv, toDailyRows, toHistoryRows, toNumber } from "./data";
import { fmt, methodName, range } from "./format";

describe("parseCsv", () => {
  it("maps header names to values and keeps empty cells", () => {
    expect(parseCsv("date,pm25\n2026-11-10,15.5\n2026-11-11,\n")).toEqual([
      { date: "2026-11-10", pm25: "15.5" },
      { date: "2026-11-11", pm25: "" },
    ]);
  });

  it("returns nothing for an empty file", () => {
    expect(parseCsv("")).toEqual([]);
  });
});

describe("toNumber", () => {
  it("treats blanks and junk as missing", () => {
    expect(toNumber("")).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber("abc")).toBeNull();
    expect(toNumber("12.5")).toBe(12.5);
  });
});

describe("chart series", () => {
  const daily = toDailyRows(
    parseCsv("date,pm25\n2026-11-08,10\n2026-11-09,\n2026-11-10,12\n2026-11-11,14\n"),
  );

  it("skips days without a measurement and keeps the latest ones", () => {
    expect(measuredSeries(daily, 2)).toEqual([
      { x: "2026-11-10", y: 12 },
      { x: "2026-11-11", y: 14 },
    ]);
  });

  it("only uses PM2.5 forecasts issued the day before, inside the measured window", () => {
    const history = toHistoryRows(
      parseCsv(
        "kind,period,label,target,value\n" +
          "daily,2026-11-07,tomorrow,pm25,9\n" +
          "daily,2026-11-11,tomorrow,pm25,13\n" +
          "daily,2026-11-11,today,pm25,99\n" +
          "daily,2026-11-11,tomorrow,pm10,99\n" +
          "monthly,2026-12,1,pm25,99\n",
      ),
    );
    expect(dayBeforeForecasts(history, measuredSeries(daily))).toEqual([{ x: "2026-11-11", y: 13 }]);
  });
});

describe("dataBase", () => {
  it("defaults to the data branch and accepts an override", () => {
    expect(dataBase("")).toContain("raw.githubusercontent.com");
    expect(dataBase("?data=http://localhost:8765")).toBe("http://localhost:8765");
  });
});

describe("formatting", () => {
  it("shows missing values as n/a", () => {
    expect(fmt(null)).toBe("n/a");
    expect(fmt(21.26)).toBe("21.3");
    expect(range(10, 20.04)).toBe("Likely 10.0 to 20.0");
    expect(methodName("random_forest")).toBe("random forest");
  });
});

describe("station page helpers", () => {
  it("reads the station id and builds the seven forecast dates", async () => {
    const { stationIdFrom, forecastDates } = await import("./data");
    expect(stationIdFrom("?id=225679&lang=th")).toBe(225679);
    expect(stationIdFrom("?id=abc")).toBeNull();
    expect(forecastDates("2026-11-30")).toEqual([
      "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04", "2026-12-05", "2026-12-06",
    ]);
  });

  it("summarises one station's scored forecasts", async () => {
    const { summarizeStation, toScoredStationRows } = await import("./data");
    const rows = toScoredStationRows([
      { location_id: "1", target: "pm25", abs_error: "2", persistence_abs_error: "4", in_range: "True" },
      { location_id: "1", target: "pm25", abs_error: "4", persistence_abs_error: "6", in_range: "False" },
      { location_id: "2", target: "pm25", abs_error: "9", persistence_abs_error: "9", in_range: "True" },
    ]);
    expect(summarizeStation(rows, 1, "pm25")).toEqual({ days: 2, mae: 3, baselineMae: 5, coverage: 0.5 });
  });

  it("writes chances so a small one never reads as zero", async () => {
    const { chanceText } = await import("./data");
    expect(chanceText(0.004)).toBe("<1%");
    expect(chanceText(0.234)).toBe("23%");
    expect(chanceText(null)).toBe("n/a");
  });
});
