"use client";

import { bandAbove, type Pollutant } from "@/lib/aqi";
import { chanceText } from "@/lib/data";
import type { ChanceAbove } from "@/lib/types";
import { useLang } from "./LangProvider";

/** One line per band edge: a dot in the colour above the edge, then the chance of going above it. */
export default function ChanceLines({ pollutant, chances }: { pollutant: Pollutant; chances: ChanceAbove[] }) {
  const { lang, t } = useLang();
  return (
    <>
      {chances.map(({ threshold, p }) => {
        const band = bandAbove(pollutant, threshold);
        return (
          <div className="chance" key={threshold}>
            {band && (
              <span className="aqi-dot small" style={{ background: band.color }} title={lang === "th" ? band.th : band.en} />
            )}
            {t("chanceAboveEdge")} {threshold}: {chanceText(p)}
          </div>
        );
      })}
    </>
  );
}
