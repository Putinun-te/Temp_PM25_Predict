import Dashboard from "@/components/Dashboard";

// The page shell is exported as static HTML. Data is fetched in the browser,
// so the site shows each morning's forecast without being rebuilt.
export default function Page() {
  return (
    <main>
      <Dashboard />
      <h2>How good is it?</h2>
      <p className="note">
        Every forecast slot is scored out of sample with walk-forward validation and only uses a model when it
        beats yesterday&apos;s value. Monthly values are seasonal averages; long-range daily forecasts are not
        attempted. Temperature and humidity are trained on Open-Meteo history, and the TMD value is the Thai
        Meteorological Department&apos;s own forecast. Details are in the{" "}
        <a href="https://github.com/Putinun-te/Temp_PM25_Predict#model-card">model card</a>.
      </p>
      <p className="note">Data: OpenAQ (Air4Thai reference stations), Open-Meteo (CC BY 4.0) and TMD.</p>
    </main>
  );
}
