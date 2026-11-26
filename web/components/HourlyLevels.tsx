"use client";

import type { CSSProperties } from "react";
import { bandAbove, bandFor } from "@/lib/aqi";
import { chanceText, hourChances, peakChances } from "@/lib/data";
import { fmt } from "@/lib/format";
import type { HourlyPoint, HourlyTarget } from "@/lib/types";
import { useLang } from "./LangProvider";

/** One coloured cell per forecast hour, so the air quality level of each hour reads at a glance. */
export default function HourlyLevels({ hours, target = "pm25" }: { hours: HourlyPoint[]; target?: HourlyTarget }) {
  const { lang, t } = useLang();
  return (
    <div className="hour-levels">
      {(["today", "tomorrow"] as const).map((day) => {
        const points = hours.filter((point) => point.day === day);
        if (points.length === 0) return null;
        const peaks = peakChances(points, target);
        return (
          <div key={day}>
            <div className="hour-row">
              <span className="hour-day">{t(day)}</span>
              <div className="hour-cells">
                {points.map((point) => {
                  const value = target === "pm10" ? (point.pm10 ?? null) : point.pm25;
                  const band = bandFor(target, value);
                  const level = band ? (lang === "th" ? band.th : band.en) : t("noData");
                  const hour = point.time.slice(11, 13);
                  const chances = hourChances(point, target)
                    .map(({ threshold, p }) => `, ${t("chanceAboveEdge")} ${threshold}: ${chanceText(p)}`)
                    .join("");
                  return (
                    <span
                      key={point.time}
                      className="hour-cell"
                      // Each hour sits in its own column, so today's shorter row lines up with tomorrow's.
                      style={
                        {
                          background: band?.color ?? "var(--line)",
                          "--start": Number(hour) + 1,
                          "--start-narrow": (Number(hour) % 12) + 1,
                        } as CSSProperties
                      }
                      title={`${point.time.replace("T", " ")}: ${fmt(value)} µg/m³, ${level}${chances}`}
                    >
                      <small>{hour}</small>
                      {fmt(value, 0)}
                    </span>
                  );
                })}
              </div>
            </div>
            {peaks.length > 0 && (
              <div className="hour-peaks">
                {peaks.map(({ threshold, p, time }) => {
                  const band = bandAbove(target, threshold);
                  return (
                    <span className="chance" key={threshold}>
                      {band && (
                        <span
                          className="aqi-dot small"
                          style={{ background: band.color }}
                          title={lang === "th" ? band.th : band.en}
                        />
                      )}
                      {t("hourlyPeakChance")} {threshold}: {chanceText(p)}
                      {/* Below 1% every hour is alike, so no hour is named. */}
                      {p >= 0.01 && ` ${t("hourlyPeakAt")} ${time.slice(11, 16)}`}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
