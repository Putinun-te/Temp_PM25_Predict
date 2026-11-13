"use client";

import { useEffect, useRef } from "react";
import { CategoryScale, Chart, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip } from "chart.js";
import type { Point } from "@/lib/types";

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Legend, Tooltip);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

interface Props {
  measured: Point[];
  forecasts: Point[];
  labels: { measured: string; forecast: string };
}

export default function HistoryChart({ measured, forecasts, labels }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    const muted = cssVar("--muted");
    const chart = new Chart(canvas.current, {
      type: "line",
      data: {
        // Forecast dates can run past the newest measurement, so the axis covers both.
        labels: Array.from(new Set([...measured, ...forecasts].map((point) => point.x))).sort(),
        datasets: [
          { label: labels.measured, data: measured, borderColor: cssVar("--text"), pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
          {
            label: labels.forecast,
            data: forecasts,
            borderColor: cssVar("--forecast"),
            backgroundColor: cssVar("--forecast"),
            showLine: false,
            pointRadius: 4,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          x: { type: "category", ticks: { maxTicksLimit: 8, color: muted } },
          y: { title: { display: true, text: "PM2.5 (µg/m³)", color: muted }, ticks: { color: muted } },
        },
        plugins: { legend: { labels: { color: muted } } },
      },
    });
    return () => chart.destroy();
  }, [measured, forecasts, labels.measured, labels.forecast]);

  return (
    <canvas
      ref={canvas}
      aria-label="Measured daily PM2.5 for the last 60 days with forecasts issued the day before"
      role="img"
    />
  );
}
