import type { Metadata } from "next";
import HowItWorks from "@/components/HowItWorks";

export const metadata: Metadata = {
  title: "How it works · Bangkok PM2.5 Forecast",
  description: "The sources, scheduled jobs and outputs behind the Bangkok PM2.5 forecast.",
};

export default function HowPage() {
  return (
    <main>
      <HowItWorks />
    </main>
  );
}
