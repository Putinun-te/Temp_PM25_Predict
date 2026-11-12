import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bangkok PM2.5 Forecast",
  description:
    "Daily PM2.5, PM10, temperature and humidity forecast for Bangkok, evaluated honestly against baselines.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
