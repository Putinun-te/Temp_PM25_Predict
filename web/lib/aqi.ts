// Thai air quality bands from the Pollution Control Department (PCD), for 24-hour
// average concentrations. They follow the PM2.5 standard of 37.5 µg/m³ in force
// since 1 June 2023. Check pcd.go.th before changing them.

export type Pollutant = "pm25" | "pm10";

export interface Band {
  level: number;
  upTo: number; // Inclusive upper bound in µg/m³; Infinity for the last band
  color: string;
  th: string;
  en: string;
  adviceTh: string;
  adviceEn: string;
}

const LABELS = [
  {
    color: "#3b9fe5",
    th: "ดีมาก",
    en: "Very good",
    adviceTh: "เหมาะกับกิจกรรมกลางแจ้งและการท่องเที่ยว",
    adviceEn: "Good for outdoor activities.",
  },
  {
    color: "#3dae4a",
    th: "ดี",
    en: "Good",
    adviceTh: "ทำกิจกรรมกลางแจ้งได้ตามปกติ",
    adviceEn: "Outdoor activities as usual.",
  },
  {
    color: "#e6c300",
    th: "ปานกลาง",
    en: "Moderate",
    adviceTh: "ผู้ที่ต้องดูแลสุขภาพเป็นพิเศษควรลดกิจกรรมกลางแจ้ง",
    adviceEn: "Sensitive groups should cut down on outdoor activity.",
  },
  {
    color: "#f08a24",
    th: "เริ่มมีผลกระทบต่อสุขภาพ",
    en: "Starting to affect health",
    adviceTh: "ลดกิจกรรมกลางแจ้ง และใช้หน้ากากป้องกันฝุ่นเมื่ออยู่นอกอาคาร",
    adviceEn: "Reduce time outdoors and wear a dust mask outside.",
  },
  {
    color: "#d93a3a",
    th: "มีผลกระทบต่อสุขภาพ",
    en: "Affects health",
    adviceTh: "ทุกคนควรงดกิจกรรมกลางแจ้ง หากมีอาการผิดปกติให้ปรึกษาแพทย์",
    adviceEn: "Everyone should avoid outdoor activity; see a doctor if you have symptoms.",
  },
];

const LIMITS: Record<Pollutant, number[]> = {
  pm25: [15, 25, 37.5, 75, Infinity],
  pm10: [50, 80, 120, 180, Infinity],
};

export const BANDS: Record<Pollutant, Band[]> = {
  pm25: LIMITS.pm25.map((upTo, i) => ({ level: i + 1, upTo, ...LABELS[i]! })),
  pm10: LIMITS.pm10.map((upTo, i) => ({ level: i + 1, upTo, ...LABELS[i]! })),
};

/** The band a daily concentration falls in, or null when there is no value. */
export function bandFor(pollutant: Pollutant, value: number | null | undefined): Band | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  // PCD publishes one decimal place, so 37.54 reads as 37.5 and stays moderate.
  const rounded = Math.round(value * 10) / 10;
  return BANDS[pollutant].find((band) => rounded <= band.upTo) ?? null;
}
