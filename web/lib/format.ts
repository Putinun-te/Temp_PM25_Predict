export function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "n/a" : value.toFixed(digits);
}

export function range(low: number | null | undefined, high: number | null | undefined, digits = 1): string {
  return `Likely ${fmt(low, digits)} to ${fmt(high, digits)}`;
}

export function methodName(method: string | undefined): string {
  return (method || "n/a").replaceAll("_", " ");
}
