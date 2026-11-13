"use client";

import { bandFor } from "@/lib/aqi";
import { fmt } from "@/lib/format";
import type { GistdaReference as Reference } from "@/lib/types";
import { AqiBadge } from "./AqiBadge";
import { useLang } from "./LangProvider";

export default function GistdaReference({ data }: { data: Reference }) {
  const { t } = useLang();
  const band = bandFor("pm25", data.pm25_24h_mean);
  const time = data.observed_at.replace("T", " ").slice(0, 16);
  return (
    <div className="card reference" style={band ? { borderLeft: `6px solid ${band.color}` } : undefined}>
      <div className="label">
        {t("gistdaTitle")} ·{" "}
        <a href="https://pm25.gistda.or.th" target="_blank" rel="noreferrer">
          pm25.gistda.or.th
        </a>
      </div>
      <div className="value">
        {fmt(data.pm25_24h_mean)}
        <span className="unit"> µg/m³</span>
      </div>
      <div className="range">
        {t("gistdaMean")} {time}, {t("gistdaHourly")} {fmt(data.pm25_hourly)}
      </div>
      <AqiBadge pollutant="pm25" value={data.pm25_24h_mean} />
      <div className="method">{t("gistdaNote")}</div>
    </div>
  );
}
