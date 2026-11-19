import type { Metadata } from "next";
import StationView from "@/components/StationView";

export const metadata: Metadata = {
  title: "Station · Bangkok PM2.5 Forecast",
  description: "One reference station: its last 14 measured days, its seven-day forecast and how its forecasts have done.",
};

// The station is chosen with ?id= and loaded in the browser, so one static page serves every station.
export default function StationPage() {
  return (
    <main>
      <StationView />
    </main>
  );
}
