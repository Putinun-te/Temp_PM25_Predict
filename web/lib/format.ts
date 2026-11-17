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
