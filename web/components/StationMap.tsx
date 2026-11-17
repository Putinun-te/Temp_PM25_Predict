"use client";

import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";
import { bandFor } from "@/lib/aqi";
import { latestStationValue } from "@/lib/data";
import { fmt } from "@/lib/format";
import type { StationForecast, StationsFile } from "@/lib/types";
import { useLang } from "./LangProvider";

const NO_DATA = "#9a9890";

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export type MapMode = "measured" | "today" | "tomorrow";

interface Props {
  data: StationsFile;
  forecasts?: StationForecast[];
  mode?: MapMode;
}

export default function StationMap({ data, forecasts = [], mode = "measured" }: Props) {
  const element = useRef<HTMLDivElement>(null);
  const { lang, t } = useLang();

  useEffect(() => {
    if (!element.current) return;
    let removed = false;
    let cleanup = () => undefined as void;
    // Leaflet touches window on import, so it loads only in the browser.
    import("leaflet").then((L) => {
      if (removed || !element.current) return;
      const map = L.map(element.current, { scrollWheelZoom: false });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map);
      const date = data.dates.at(-1) ?? "";
      const points: [number, number][] = [];
      for (const station of data.stations) {
        const measured = latestStationValue(station.pm25);
        const pm10 = latestStationValue(station.pm10);
        const forecast = forecasts.find((item) => item.location_id === station.location_id);
        // The disc shows the selected value; the popup always lists all three.
        const pm25 = mode === "measured" ? measured : (forecast?.[mode]?.pm25 ?? null);
        const band = bandFor("pm25", pm25);
        const position: [number, number] = [station.latitude, station.longitude];
        points.push(position);
        const label = band ? (lang === "th" ? band.th : band.en) : t("noData");
        const lines = [
          `<strong>${escapeHtml(station.name)}</strong>`,
          escapeHtml(station.locality),
          `${t("mapMeasured")} ${date}: PM2.5 ${measured === null ? t("noData") : `${fmt(measured)} µg/m³`}`,
        ];
        for (const key of ["today", "tomorrow"] as const) {
          const value = forecast?.[key];
          if (value && value.pm25 !== null) {
            lines.push(`${t(key === "today" ? "mapToday" : "mapTomorrow")}: ${fmt(value.pm25)} (${fmt(value.low)}–${fmt(value.high)})`);
          }
        }
        lines.push(label);
        if (station.pm10) lines.push(`PM10 ${pm10 === null ? t("noData") : `${fmt(pm10)} µg/m³`}`);
        for (const key of ["today", "tomorrow"] as const) {
          const value = forecast?.[key]?.pm10;
          if (value && value.pm10 !== null) {
            lines.push(`PM10 ${t(key === "today" ? "mapToday" : "mapTomorrow")}: ${fmt(value.pm10)} (${fmt(value.low)}–${fmt(value.high)})`);
          }
        }
        // A coloured disc with the value inside, readable without opening the popup.
        const icon = L.divIcon({
          className: "station-marker",
          html: `<span style="background:${band?.color ?? NO_DATA}">${pm25 === null ? "–" : fmt(pm25, 0)}</span>`,
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        });
        L.marker(position, { icon, title: station.name }).bindPopup(lines.join("<br>")).addTo(map);
      }
      if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [24, 24] });
      cleanup = () => map.remove();
    });
    return () => {
      removed = true;
      cleanup();
    };
  }, [data, forecasts, mode, lang, t]);

  return <div ref={element} className="map" role="region" aria-label={t("stationsMap")} />;
}
