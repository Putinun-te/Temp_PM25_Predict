export type Lang = "th" | "en";

export const LANGS: Lang[] = ["th", "en"];

const STRINGS = {
  title: { en: "Bangkok PM2.5 forecast", th: "พยากรณ์ PM2.5 กรุงเทพฯ" },
  navForecast: { en: "Forecast", th: "พยากรณ์" },
  navAccuracy: { en: "Live accuracy", th: "ความแม่นจริง" },
  loading: { en: "Loading…", th: "กำลังโหลด…" },
  forDate: { en: "For", th: "สำหรับวันที่" },
  generated: { en: "generated", th: "สร้างเมื่อ" },
  dataUpTo: { en: "station data up to", th: "ข้อมูลสถานีถึง" },
  dataCurrent: { en: "Data current", th: "ข้อมูลล่าสุด" },
  daysOld: { en: "days old", th: "วันที่แล้ว" },
  dataOld: { en: "Data", th: "ข้อมูลเก่า" },
  loadError: { en: "Could not load the forecast data", th: "โหลดข้อมูลพยากรณ์ไม่ได้" },
  todayTomorrow: { en: "Today and tomorrow", th: "วันนี้และพรุ่งนี้" },
  today: { en: "Today", th: "วันนี้" },
  tomorrow: { en: "Tomorrow", th: "พรุ่งนี้" },
  temperature: { en: "Temperature", th: "อุณหภูมิ" },
  humidity: { en: "Humidity", th: "ความชื้น" },
  likely: { en: "Likely", th: "น่าจะอยู่ระหว่าง" },
  to: { en: "to", th: "ถึง" },
  measuredVsForecast: { en: "Measured PM2.5 against our forecast", th: "PM2.5 ที่วัดได้ เทียบกับค่าพยากรณ์" },
  chartNote: {
    en: "The line is the measured Bangkok daily median from Air4Thai reference stations. Dots are the forecast issued one day earlier for that date.",
    th: "เส้นคือค่ามัธยฐานรายวันของกรุงเทพฯ จากสถานีตรวจวัด Air4Thai จุดคือค่าที่พยากรณ์ไว้ล่วงหน้าหนึ่งวันสำหรับวันนั้น",
  },
  measured: { en: "Measured", th: "ค่าที่วัดได้" },
  forecastDayBefore: { en: "Forecast (issued day before)", th: "พยากรณ์ (ออกล่วงหน้าหนึ่งวัน)" },
  stationsMap: { en: "Stations, yesterday's PM2.5", th: "ค่า PM2.5 เมื่อวานรายสถานี" },
  mapNote: {
    en: "Daily mean of each reference station. Grey means fewer than 18 hourly readings.",
    th: "ค่าเฉลี่ยรายวันของแต่ละสถานี สีเทาคือมีข้อมูลรายชั่วโมงไม่ถึง 18 ชั่วโมง",
  },
  noData: { en: "no data", th: "ไม่มีข้อมูล" },
  nextMonths: { en: "Next three months", th: "สามเดือนข้างหน้า" },
  month: { en: "Month", th: "เดือน" },
  aqiScale: { en: "Thai air quality scale (PCD), 24-hour average", th: "เกณฑ์คุณภาพอากาศของกรมควบคุมมลพิษ ค่าเฉลี่ย 24 ชั่วโมง" },
  howGood: { en: "How good is it?", th: "แม่นแค่ไหน" },
  howGoodText: {
    en: "Every forecast slot is scored out of sample with walk-forward validation and only uses a model when it beats yesterday's value. Monthly values are seasonal averages. Temperature and humidity are trained on Open-Meteo history, and the TMD value is the Thai Meteorological Department's own forecast.",
    th: "ทุกค่าพยากรณ์ผ่านการทดสอบแบบ walk-forward กับข้อมูลที่โมเดลไม่เคยเห็น และจะใช้โมเดลก็ต่อเมื่อแม่นกว่าการใช้ค่าของเมื่อวาน ค่ารายเดือนเป็นค่าเฉลี่ยตามฤดูกาล อุณหภูมิและความชื้นฝึกจากข้อมูลย้อนหลังของ Open-Meteo ส่วนค่า TMD คือพยากรณ์ของกรมอุตุนิยมวิทยา",
  },
  modelCard: { en: "model card", th: "รายละเอียดโมเดล" },
  apiNote: { en: "The data is also available as a JSON API:", th: "ข้อมูลทั้งหมดเรียกใช้ผ่าน JSON API ได้ที่" },
  sources: {
    en: "Data: OpenAQ (Air4Thai reference stations), Open-Meteo (CC BY 4.0) and TMD.",
    th: "ข้อมูล: OpenAQ (สถานี Air4Thai), Open-Meteo (CC BY 4.0) และกรมอุตุนิยมวิทยา",
  },
  accuracyTitle: { en: "Live accuracy", th: "ความแม่นจากการใช้งานจริง" },
  accuracyIntro: {
    en: "Forecasts that were actually published, scored once the measured value arrived. Persistence means using the newest measured day as the forecast; skill above 0 means the forecast beat it.",
    th: "คะแนนของค่าพยากรณ์ที่เผยแพร่จริง เมื่อมีค่าที่วัดได้ของวันนั้นแล้ว Persistence คือการใช้ค่าวันล่าสุดที่วัดได้เป็นค่าพยากรณ์ ค่า skill มากกว่า 0 แปลว่าพยากรณ์ของเราแม่นกว่า",
  },
  latestScored: { en: "Latest scored date", th: "วันล่าสุดที่ให้คะแนนแล้ว" },
  window: { en: "Window", th: "ช่วง" },
  days: { en: "days", th: "วัน" },
  target: { en: "Target", th: "ค่า" },
  horizon: { en: "Horizon", th: "ล่วงหน้า" },
  source: { en: "Source", th: "แหล่ง" },
  scored: { en: "Days scored", th: "จำนวนวัน" },
  mae: { en: "MAE", th: "MAE" },
  persistenceMae: { en: "Persistence MAE", th: "MAE ของ persistence" },
  skill: { en: "Skill", th: "Skill" },
  coverage: { en: "Inside range", th: "อยู่ในช่วงที่คาด" },
  ourForecast: { en: "Our forecast", th: "พยากรณ์ของเรา" },
  tmd: { en: "TMD", th: "กรมอุตุฯ" },
  alerts: { en: "Alerts", th: "การแจ้งเตือน" },
  noScores: { en: "No published forecast has been scored yet.", th: "ยังไม่มีค่าพยากรณ์ที่ให้คะแนนได้" },
  recentErrors: { en: "Recent PM2.5 forecasts for tomorrow", th: "พยากรณ์ PM2.5 วันพรุ่งนี้ล่าสุด" },
  date: { en: "Date", th: "วันที่" },
  forecast: { en: "Forecast", th: "พยากรณ์" },
  actual: { en: "Measured", th: "วัดได้" },
  error: { en: "Error", th: "คลาดเคลื่อน" },
  gistdaTitle: { en: "GISTDA satellite estimate for Bangkok", th: "ค่าประมาณจากดาวเทียมของ GISTDA กรุงเทพฯ" },
  gistdaMean: { en: "24-hour average to", th: "ค่าเฉลี่ย 24 ชั่วโมง ถึง" },
  gistdaHourly: { en: "latest hour", th: "ชั่วโมงล่าสุด" },
  gistdaNote: {
    en: "A reference from GISTDA's satellite and model estimate, not a station measurement and not used by our model.",
    th: "ค่าอ้างอิงจากการประมาณด้วยดาวเทียมและแบบจำลองของ GISTDA ไม่ใช่ค่าจากสถานีตรวจวัด และไม่ได้ใช้ในโมเดลของเรา",
  },
} as const;

export type StringKey = keyof typeof STRINGS;

export function translate(lang: Lang, key: StringKey): string {
  return STRINGS[key][lang];
}

/** Language from `?lang=`, then the saved choice, then the browser. */
export function pickLang(search: string, saved: string | null, browser: string | undefined): Lang {
  const query = new URLSearchParams(search).get("lang");
  for (const candidate of [query, saved]) {
    if (candidate === "th" || candidate === "en") return candidate;
  }
  return browser?.toLowerCase().startsWith("th") ? "th" : "en";
}
