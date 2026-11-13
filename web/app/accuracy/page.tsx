import type { Metadata } from "next";
import AccuracyView from "@/components/AccuracyView";

export const metadata: Metadata = {
  title: "Live accuracy · Bangkok PM2.5 Forecast",
  description: "How the published Bangkok PM2.5 forecasts compared with what was measured.",
};

export default function AccuracyPage() {
  return (
    <main>
      <AccuracyView />
    </main>
  );
}
