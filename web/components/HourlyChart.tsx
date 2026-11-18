"use client";

import { useEffect, useRef } from "react";
import { CategoryScale, Chart, Filler, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip } from "chart.js";
import { hourLabel } from "@/lib/data";
import type { HourlyForecast, HourlyPoint, HourlyTarget } from "@/lib/types";

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Legend, Tooltip, Filler);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

interface Props {
  data: HourlyForecast;
  labels: { measured: string; forecast: string; range: string };
  target?: HourlyTarget;
}

const NAMES: Record<HourlyTarget, string> = { pm25: "PM2.5", pm10: "PM10" };

/** The value, low and high of one hour for the chosen target. */
function pick(point: HourlyPoint, target: HourlyTarget): [number | null, number | null, number | null] {
  if (target === "pm10") return [point.pm10 ?? null, point.pm10_low ?? null, point.pm10_high ?? null];
  return [point.pm25, point.low, point.high];
}

export default function HourlyChart({ data, labels, target = "pm25" }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    const muted = cssVar("--muted");
    const forecastColor = cssVar("--forecast");
    const times = [...data.measured.map((point) => point.time), ...data.hours.map((point) => point.time)];
    const gap = data.measured.map(() => null);
    const measured = [...data.measured.map((point) => point[target] ?? null), ...data.hours.map(() => null)];
    const values = data.hours.map((point) => pick(point, target));
    const chart = new Chart(canvas.current, {
      type: "line",
      data: {
        labels: times.map(hourLabel),
        datasets: [
          { label: labels.measured, data: measured, borderColor: cssVar("--text"), borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
          { label: labels.forecast, data: [...gap, ...values.map((v) => v[0])], borderColor: forecastColor, borderWidth: 2, pointRadius: 0, tension: 0.3 },
          // The band is drawn as the high line filled down to the low line.
          { label: labels.range, data: [...gap, ...values.map((v) => v[2])], borderWidth: 0, pointRadius: 0, tension: 0.3, fill: "+1", backgroundColor: `${forecastColor}33` },
          { label: "", data: [...gap, ...values.map((v) => v[1])], borderWidth: 0, pointRadius: 0, tension: 0.3 },
        ],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { ticks: { maxTicksLimit: 9, color: muted } },
          y: { beginAtZero: true, title: { display: true, text: `${NAMES[target]} (µg/m³)`, color: muted }, ticks: { color: muted } },
        },
        plugins: {
          legend: { labels: { color: muted, filter: (item) => item.text !== "" } },
          tooltip: { filter: (item) => item.dataset.label !== "" },
        },
      },
    });
    return () => chart.destroy();
  }, [data, target, labels.measured, labels.forecast, labels.range]);

  return <canvas ref={canvas} role="img" aria-label={`Hourly ${NAMES[target]}: the last measured hours and the forecast for today and tomorrow`} />;
}
