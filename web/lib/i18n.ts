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
  inDays: { en: "In {n} days", th: "อีก {n} วัน" },
  weekTitle: { en: "Next 7 days", th: "7 วันข้างหน้า" },
  weekNote: {
    en: "Daily means with the range that held 80% of past errors. Ranges widen with each day ahead. A day shows a model only where it beat simple rules in testing; otherwise it shows the best simple rule, named under the value.",
    th: "ค่าเฉลี่ยรายวันพร้อมช่วงที่ครอบคลุม 80% ของค่าคลาดเคลื่อนในอดีต ยิ่งไกลช่วงยิ่งกว้าง วันไหนโมเดลชนะวิธีพื้นฐานในการทดสอบจึงใช้โมเดล ไม่งั้นใช้วิธีพื้นฐานที่ดีที่สุด ชื่อวิธีอยู่ใต้ตัวเลข",
  },
  day: { en: "Day", th: "วัน" },
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
  extraTitle: { en: "Hourly and station PM2.5 forecasts", th: "พยากรณ์ PM2.5 รายชั่วโมงและรายสถานี" },
  extraIntro: {
    en: "Hourly rows count scored hours and compare with the same hour of the previous day. Station rows count station-days and compare with each station's last measured day.",
    th: "แถวรายชั่วโมงนับจำนวนชั่วโมงที่วัดค่าได้แล้ว เทียบกับชั่วโมงเดียวกันของวันก่อน แถวรายสถานีนับสถานี-วัน เทียบกับค่าวันล่าสุดของสถานีนั้น",
  },
  kind: { en: "Forecast", th: "พยากรณ์" },
  kindHourly: { en: "Hourly (city)", th: "รายชั่วโมง (ทั้งเมือง)" },
  kindStations: { en: "Per station", th: "รายสถานี" },
  kindHourlyAfternoon: { en: "Hourly, afternoon update", th: "รายชั่วโมง รอบบ่าย" },
  kindStationsPm10: { en: "Per station, PM10", th: "รายสถานี PM10" },
  kindHourlyPm10: { en: "Hourly PM10 (city)", th: "PM10 รายชั่วโมง (ทั้งเมือง)" },
  kindHourlyPm10Afternoon: { en: "Hourly PM10, afternoon update", th: "PM10 รายชั่วโมง รอบบ่าย" },
  kindHourlyEvening: { en: "Hourly, evening update", th: "รายชั่วโมง รอบเย็น" },
  kindHourlyPm10Evening: { en: "Hourly PM10, evening update", th: "PM10 รายชั่วโมง รอบเย็น" },
  baselineMae: { en: "Baseline MAE", th: "MAE วิธีพื้นฐาน" },
  recentErrors: { en: "Recent PM2.5 forecasts for tomorrow", th: "พยากรณ์ PM2.5 วันพรุ่งนี้ล่าสุด" },
  date: { en: "Date", th: "วันที่" },
  forecast: { en: "Forecast", th: "พยากรณ์" },
  actual: { en: "Measured", th: "วัดได้" },
  error: { en: "Error", th: "คลาดเคลื่อน" },
  gistdaTitle: { en: "GISTDA satellite estimate for Bangkok", th: "ค่าประมาณจากดาวเทียมของ GISTDA กรุงเทพฯ" },
  gistdaMean: { en: "24-hour average to", th: "ค่าเฉลี่ย 24 ชั่วโมง ถึง" },
  gistdaHourly: { en: "latest hour", th: "ชั่วโมงล่าสุด" },
  yesterdayTitle: { en: "Latest measured day: forecast against measured", th: "วันล่าสุดที่วัดได้: ค่าที่ทายไว้เทียบกับค่าจริง" },
  measuredOn: { en: "Measured", th: "วัดได้จริง" },
  issuedSameDay: { en: "Forecast that morning", th: "ทายไว้เช้าวันนั้น" },
  issuedDayBefore: { en: "Forecast the day before", th: "ทายไว้ล่วงหน้า 1 วัน" },
  pastDaysTitle: { en: "Last 7 measured days: forecast against measured", th: "ย้อนหลัง 7 วัน: ค่าที่ทายไว้เทียบกับค่าจริง" },
  pastDaysNote: {
    en: "Each row is one measured day with the two forecasts made for it. Days appear as their measurements arrive; the record starts on 11 November 2026.",
    th: "แต่ละแถวคือวันที่วัดค่าได้แล้ว พร้อมค่าที่ทายไว้สองครั้งสำหรับวันนั้น วันใหม่จะขึ้นเมื่อค่าวัดมาถึง บันทึกเริ่มวันที่ 11 พ.ย. 2026",
  },
  tooHigh: { en: "too high by", th: "สูงไป" },
  tooLow: { en: "too low by", th: "ต่ำไป" },
  exact: { en: "exact", th: "ตรงพอดี" },
  notIssued: { en: "not issued", th: "ไม่ได้ออกพยากรณ์" },
  yesterdayNote: {
    en: "Station data arrives a day late, so the newest measured day is usually yesterday. Today's forecast can only be checked tomorrow, once the day is complete. Match is 100% minus the error as a share of the measured value.",
    th: "ข้อมูลสถานีมาช้าหนึ่งวัน วันล่าสุดที่วัดได้จึงมักเป็นเมื่อวาน ค่าที่ทายของวันนี้จะเทียบได้พรุ่งนี้เมื่อครบทั้งวัน เปอร์เซ็นต์ที่ตรงคือ 100% ลบค่าคลาดเคลื่อนเทียบกับค่าที่วัดได้จริง",
  },
  match: { en: "match", th: "ตรง" },
  matchAverage: { en: "Average match", th: "ตรงเฉลี่ย" },
  hourlyTitle: { en: "Hourly forecast, today and tomorrow", th: "พยากรณ์รายชั่วโมง วันนี้และพรุ่งนี้" },
  hourlyNote: {
    en: "Made each morning from station hours up to 03:00, then again at about 13:00 from hours up to 09:00 and at about 19:00 from hours up to 16:00. The shaded band is where 80% of past forecasts landed. Hourly values swing more than the daily average.",
    th: "พยากรณ์ตอนเช้าจากข้อมูลสถานีถึง 03:00 อัปเดตราว 13:00 จากข้อมูลถึง 09:00 และราว 19:00 จากข้อมูลถึง 16:00 แถบสีคือช่วงที่ 80% ของการพยากรณ์ที่ผ่านมาอยู่ในนั้น ค่ารายชั่วโมงแกว่งมากกว่าค่าเฉลี่ยรายวัน",
  },
  hourlyInputs: { en: "Uses measurements through", th: "ใช้ค่าวัดถึง" },
  hourlyLevelsNote: {
    en: "Colours apply the PCD bands to each hour's value. The official index uses the 24-hour average, so treat these as a guide to the time of day, not as the official level.",
    th: "สีใช้เกณฑ์ของกรมควบคุมมลพิษกับค่าของแต่ละชั่วโมง ดัชนีทางการใช้ค่าเฉลี่ย 24 ชั่วโมง จึงควรใช้ดูช่วงเวลาของวัน ไม่ใช่ระดับทางการ",
  },
  hourlyForecast: { en: "Hourly forecast", th: "พยากรณ์รายชั่วโมง" },
  hourlyRange: { en: "Likely range", th: "ช่วงที่น่าจะเป็น" },
  mapMeasured: { en: "Measured", th: "วัดได้ล่าสุด" },
  mapToday: { en: "Forecast today", th: "พยากรณ์วันนี้" },
  mapTomorrow: { en: "Forecast tomorrow", th: "พยากรณ์พรุ่งนี้" },
  stationsTitle: { en: "Stations", th: "รายสถานี" },
  stationDetails: { en: "Details", th: "ดูรายละเอียด" },
  stationPick: { en: "Station", th: "สถานี" },
  stationNotFound: { en: "Choose a station from the list.", th: "เลือกสถานีจากรายการ" },
  stationChartTitle: { en: "Last 14 days and the next 7", th: "14 วันที่ผ่านมาและ 7 วันข้างหน้า" },
  stationForecastTitle: { en: "Forecast for this station", th: "พยากรณ์ของสถานีนี้" },
  stationAccuracyTitle: { en: "How this station's forecasts have done", th: "ความแม่นของพยากรณ์สถานีนี้" },
  stationAccuracyNote: {
    en: "Forecasts published since 17 November 2026 and scored once the day was measured. Baseline is the station's own last measured day.",
    th: "พยากรณ์ที่เผยแพร่ตั้งแต่ 17 พ.ย. 2026 และเทียบเมื่อวัดค่าวันนั้นได้แล้ว วิธีพื้นฐานคือค่าวันล่าสุดที่สถานีนี้วัดได้",
  },
  stationNoScores: { en: "No forecasts for this station have been scored yet.", th: "ยังไม่มีพยากรณ์ของสถานีนี้ที่เทียบกับค่าจริงได้" },
  stationNote: {
    en: "Daily means. The line is what the station measured; the band is where 80% of past forecasts landed. Dots are the forecasts made the day before for days already measured.",
    th: "ค่าเฉลี่ยรายวัน เส้นคือค่าที่สถานีวัดได้ แถบสีคือช่วงที่ 80% ของการพยากรณ์ที่ผ่านมาอยู่ในนั้น จุดคือค่าที่ทายไว้ล่วงหน้าหนึ่งวันสำหรับวันที่วัดค่าได้แล้ว",
  },
  chanceAbove: { en: "Chance above standard", th: "โอกาสเกินมาตรฐาน" },
  chanceAboveShort: { en: "Above standard:", th: "โอกาสเกินมาตรฐาน:" },
  chanceAboveNote: {
    en: "Chance that the daily mean goes above the Thai 24-hour standard (PM2.5 37.5 µg/m³, PM10 120 µg/m³), from how far past forecasts at the same level missed.",
    th: "โอกาสที่ค่าเฉลี่ยรายวันจะเกินมาตรฐาน 24 ชั่วโมงของไทย (PM2.5 37.5 µg/m³, PM10 120 µg/m³) คำนวณจากความคลาดเคลื่อนของการพยากรณ์ที่ผ่านมาที่ระดับใกล้เคียงกัน",
  },
  scoredDays: { en: "Scored days", th: "จำนวนวันที่เทียบแล้ว" },
  withinRange: { en: "Within range", th: "อยู่ในช่วง" },
  backToMap: { en: "Back to the forecast", th: "กลับไปหน้าพยากรณ์" },
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
