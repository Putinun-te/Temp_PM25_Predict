"use client";

import { useEffect, useState } from "react";
import { accuracyTable, recentScored } from "@/lib/accuracy";
import { dataBase, loadAccuracy } from "@/lib/data";
import { fmt } from "@/lib/format";
import type { AccuracySummary, ScoredForecast } from "@/lib/types";
import { useLang } from "./LangProvider";

const TARGET_NAMES: Record<string, { en: string; th: string }> = {
  pm25: { en: "PM2.5", th: "PM2.5" },
  pm10: { en: "PM10", th: "PM10" },
  temp_c: { en: "Temperature", th: "อุณหภูมิ" },
  rh_pct: { en: "Humidity", th: "ความชื้น" },
};

function percent(value: number | null): string {
  return value === null ? "n/a" : `${Math.round(value * 100)}%`;
}

export default function AccuracyView() {
  const { lang, t } = useLang();
  const [summary, setSummary] = useState<AccuracySummary | null>(null);
  const [scored, setScored] = useState<ScoredForecast[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [windowDays, setWindowDays] = useState(30);

  useEffect(() => {
    loadAccuracy(dataBase(window.location.search)).then((result) => {
      setSummary(result.summary);
      setScored(result.scored);
      setLoaded(true);
    });
  }, []);

  const rows = summary ? accuracyTable(summary, windowDays) : [];
  const recent = recentScored(scored, "pm25", "tomorrow", 14);

  return (
    <>
      <h1>{t("accuracyTitle")}</h1>
      <p className="sub">
        {summary?.latest_scored ? `${t("latestScored")}: ${summary.latest_scored}` : loaded ? "" : t("loading")}
      </p>
      <p className="note">{t("accuracyIntro")}</p>

      {loaded && rows.length === 0 && <p className="note">{t("noScores")}</p>}

      {summary && summary.alerts.length > 0 && (
        <div className="alert" role="status">
          <strong>{t("alerts")}</strong>
          <ul>
            {summary.alerts.map((alert) => (
              <li key={alert}>{alert}</li>
            ))}
          </ul>
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="lang" role="group" aria-label={t("window")}>
            {(summary?.windows ?? [7, 30, 90]).map((days) => (
              <button key={days} type="button" aria-pressed={windowDays === days} className={windowDays === days ? "active" : ""} onClick={() => setWindowDays(days)}>
                {days} {t("days")}
              </button>
            ))}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("target")}</th>
                  <th>{t("horizon")}</th>
                  <th>{t("source")}</th>
                  <th>{t("scored")}</th>
                  <th>{t("mae")}</th>
                  <th>{t("persistenceMae")}</th>
                  <th>{t("skill")}</th>
                  <th>{t("coverage")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const skill = row.skill_vs_persistence;
                  return (
                    <tr key={`${row.target}-${row.label}-${row.source}`}>
                      <td>{TARGET_NAMES[row.target]?.[lang] ?? row.target}</td>
                      <td>{row.label === "today" ? t("today") : t("tomorrow")}</td>
                      <td>{row.source === "tmd" ? t("tmd") : t("ourForecast")}</td>
                      <td>{row.n}</td>
                      <td>{fmt(row.mae, 2)}</td>
                      <td>{fmt(row.persistence_mae, 2)}</td>
                      <td className={skill === null ? "" : skill > 0 ? "good" : "bad"}>{percent(skill)}</td>
                      <td>{row.source === "tmd" ? "–" : percent(row.coverage)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {recent.length > 0 && (
        <>
          <h2>{t("recentErrors")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("date")}</th>
                  <th>{t("forecast")}</th>
                  <th>{t("actual")}</th>
                  <th>{t("error")}</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((row) => (
                  <tr key={row.period}>
                    <td>{row.period}</td>
                    <td>{fmt(row.forecast)}</td>
                    <td>{fmt(row.actual)}</td>
                    <td>{fmt(row.abs_error)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
