export function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "n/a" : value.toFixed(digits);
}

export function range(low: number | null | undefined, high: number | null | undefined, digits = 1): string {
  return `Likely ${fmt(low, digits)} to ${fmt(high, digits)}`;
}

export function methodName(method: string | undefined): string {
  return (method || "n/a").replaceAll("_", " ");
}

/** "today", "tomorrow", or "dayN" (N days after today) as words in the page language. */
export function dayLabel(label: string, t: (key: "today" | "tomorrow" | "inDays") => string): string {
  if (label === "today" || label === "tomorrow") return t(label);
  const days = /^day(\d+)$/.exec(label)?.[1];
  return days ? t("inDays").replace("{n}", days) : label;
}

/** Corrections smaller than this round to nothing at one decimal place, so they are not shown. */
const MIN_SHOWN_BIAS = 0.05;

/** "Adjusted +0.5 °C …" when the temperature forecast carries a bias correction, else null. */
export function biasNote(bias: number | null | undefined, t: (key: "biasNote") => string): string | null {
  if (bias === null || bias === undefined || Number.isNaN(bias) || Math.abs(bias) < MIN_SHOWN_BIAS) return null;
  return t("biasNote").replace("{b}", `${bias > 0 ? "+" : "−"}${Math.abs(bias).toFixed(1)}`);
}
