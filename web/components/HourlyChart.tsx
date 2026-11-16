"use client";

import { useEffect, useRef } from "react";
import { CategoryScale, Chart, Filler, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip } from "chart.js";
import { hourLabel } from "@/lib/data";
import type { HourlyForecast } from "@/lib/types";

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Legend, Tooltip, Filler);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

interface Props {
  data: HourlyForecast;
  labels: { measured: string; forecast: string; range: string };
}

export default function HourlyChart({ data, labels }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    const muted = cssVar("--muted");
    const forecastColor = cssVar("--forecast");
    const times = [...data.measured.map((point) => point.time), ...data.hours.map((point) => point.time)];
    const gap = data.measured.map(() => null);
    const measured = [...data.measured.map((point) => point.pm25), ...data.hours.map(() => null)];
    const chart = new Chart(canvas.current, {
      type: "line",
      data: {
        labels: times.map(hourLabel),
        datasets: [
          { label: labels.measured, data: measured, borderColor: cssVar("--text"), borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
          { label: labels.forecast, data: [...gap, ...data.hours.map((p) => p.pm25)], borderColor: forecastColor, borderWidth: 2, pointRadius: 0, tension: 0.3 },
          // The band is drawn as the high line filled down to the low line.
          { label: labels.range, data: [...gap, ...data.hours.map((p) => p.high)], borderWidth: 0, pointRadius: 0, tension: 0.3, fill: "+1", backgroundColor: `${forecastColor}33` },
          { label: "", data: [...gap, ...data.hours.map((p) => p.low)], borderWidth: 0, pointRadius: 0, tension: 0.3 },
        ],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { ticks: { maxTicksLimit: 9, color: muted } },
          y: { beginAtZero: true, title: { display: true, text: "PM2.5 (µg/m³)", color: muted }, ticks: { color: muted } },
        },
        plugins: {
          legend: { labels: { color: muted, filter: (item) => item.text !== "" } },
          tooltip: { filter: (item) => item.dataset.label !== "" },
        },
      },
    });
    return () => chart.destroy();
  }, [data, labels.measured, labels.forecast, labels.range]);

  return <canvas ref={canvas} role="img" aria-label="Hourly PM2.5: the last measured hours and the forecast for today and tomorrow" />;
}
