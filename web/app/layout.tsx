import type { Metadata } from "next";
import Header from "@/components/Header";
import { LangProvider } from "@/components/LangProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bangkok PM2.5 Forecast",
  description:
    "Daily PM2.5, PM10, temperature and humidity forecast for Bangkok, evaluated honestly against baselines.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LangProvider>
          <Header />
          {children}
        </LangProvider>
      </body>
    </html>
  );
}
