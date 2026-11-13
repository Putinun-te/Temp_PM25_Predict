"use client";

import { BANDS, bandFor, type Pollutant } from "@/lib/aqi";
import { useLang } from "./LangProvider";

export function AqiBadge({ pollutant, value }: { pollutant: Pollutant; value: number | null | undefined }) {
  const { lang } = useLang();
  const band = bandFor(pollutant, value);
  if (!band) return null;
  return (
    <div className="aqi">
      <span className="aqi-dot" style={{ background: band.color }} aria-hidden="true" />
      <span>
        <strong>{lang === "th" ? band.th : band.en}</strong>
        <span className="aqi-advice">{lang === "th" ? band.adviceTh : band.adviceEn}</span>
      </span>
    </div>
  );
}

export function AqiLegend() {
  const { lang, t } = useLang();
  const pm10 = BANDS.pm10;
  return (
    <div className="legend">
      <p className="note">{t("aqiScale")}</p>
      <div className="legend-row">
        {BANDS.pm25.map((band, i) => {
          const from = i === 0 ? 0 : BANDS.pm25[i - 1]!.upTo + 0.1;
          const fromPm10 = i === 0 ? 0 : pm10[i - 1]!.upTo + 1;
          const pm25Range = Number.isFinite(band.upTo) ? `${from}–${band.upTo}` : `≥ ${from}`;
          const pm10Range = Number.isFinite(pm10[i]!.upTo) ? `${fromPm10}–${pm10[i]!.upTo}` : `≥ ${fromPm10}`;
          return (
            <div key={band.level} className="legend-item" style={{ borderTopColor: band.color }}>
              <strong>{lang === "th" ? band.th : band.en}</strong>
              <span>PM2.5 {pm25Range}</span>
              <span>PM10 {pm10Range}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
