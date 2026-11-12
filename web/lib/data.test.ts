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
