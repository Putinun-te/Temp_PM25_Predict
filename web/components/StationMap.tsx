"use client";

import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";
import { bandFor } from "@/lib/aqi";
import { latestStationValue } from "@/lib/data";
import { fmt } from "@/lib/format";
import type { StationsFile } from "@/lib/types";
import { useLang } from "./LangProvider";

const NO_DATA = "#9a9890";

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export default function StationMap({ data }: { data: StationsFile }) {
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
        const pm25 = latestStationValue(station.pm25);
        const pm10 = latestStationValue(station.pm10);
        const band = bandFor("pm25", pm25);
        const position: [number, number] = [station.latitude, station.longitude];
        points.push(position);
        const label = band ? (lang === "th" ? band.th : band.en) : t("noData");
        const lines = [
          `<strong>${escapeHtml(station.name)}</strong>`,
          `${escapeHtml(station.locality)} · ${date}`,
          `PM2.5 ${pm25 === null ? t("noData") : `${fmt(pm25)} µg/m³`} (${label})`,
        ];
        if (station.pm10) lines.push(`PM10 ${pm10 === null ? t("noData") : `${fmt(pm10)} µg/m³`}`);
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
  }, [data, lang, t]);

  return <div ref={element} className="map" role="region" aria-label={t("stationsMap")} />;
}
