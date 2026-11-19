"use client";

import { useEffect, useRef } from "react";
import { CategoryScale, Chart, Filler, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip } from "chart.js";
import type { HourlyTarget } from "@/lib/types";

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Legend, Tooltip, Filler);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export interface StationSeries {
  dates: string[];
  measured: (number | null)[];
  dayBefore: (number | null)[];
  forecast: (number | null)[];
  low: (number | null)[];
  high: (number | null)[];
}

interface Props {
  series: StationSeries;
  target: HourlyTarget;
  labels: { measured: string; forecast: string; range: string; dayBefore: string };
}

const NAMES: Record<HourlyTarget, string> = { pm25: "PM2.5", pm10: "PM10" };

export default function StationChart({ series, target, labels }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    const muted = cssVar("--muted");
    const forecastColor = cssVar("--forecast");
    const chart = new Chart(canvas.current, {
      type: "line",
      data: {
        labels: series.dates.map((date) => date.slice(5)),
        datasets: [
          { label: labels.measured, data: series.measured, borderColor: cssVar("--text"), borderWidth: 1.5, pointRadius: 2, tension: 0.3, spanGaps: false },
          { label: labels.dayBefore, data: series.dayBefore, borderColor: forecastColor, backgroundColor: forecastColor, borderWidth: 1, pointRadius: 4, pointBackgroundColor: forecastColor, showLine: false },
          { label: labels.forecast, data: series.forecast, borderColor: forecastColor, borderWidth: 2, pointRadius: 2, tension: 0.3 },
          // The band is drawn as the high line filled down to the low line.
          { label: labels.range, data: series.high, borderWidth: 0, pointRadius: 0, tension: 0.3, fill: "+1", backgroundColor: `${forecastColor}33` },
          { label: "", data: series.low, borderWidth: 0, pointRadius: 0, tension: 0.3 },
        ],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { ticks: { maxTicksLimit: 11, color: muted } },
          y: { beginAtZero: true, title: { display: true, text: `${NAMES[target]} (µg/m³)`, color: muted }, ticks: { color: muted } },
        },
        plugins: {
          legend: { labels: { color: muted, filter: (item) => item.text !== "" } },
          tooltip: { filter: (item) => item.dataset.label !== "" },
        },
      },
    });
    return () => chart.destroy();
  }, [series, target, labels.measured, labels.forecast, labels.range, labels.dayBefore]);

  return <canvas ref={canvas} role="img" aria-label={`${NAMES[target]} at this station: the last 14 measured days and the forecast for the next 7`} />;
}
