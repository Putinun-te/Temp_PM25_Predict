// Reads the public data branch, the same files the dashboard uses.
// Files are cached in memory for a few minutes, so a busy minute costs one
// download per instance, not one per request.

export const DATA_BASE =
  process.env.PM25_DATA_BASE || "https://raw.githubusercontent.com/Putinun-te/Temp_PM25_Predict/data";

const TTL_MS = 10 * 60 * 1000;
const cache = new Map<string, { at: number; text: string }>();

export class UpstreamError extends Error {}

export async function fetchText(path: string, fetcher: typeof fetch = fetch, now = Date.now()): Promise<string> {
  const hit = cache.get(path);
  if (hit && now - hit.at < TTL_MS) return hit.text;
  const response = await fetcher(`${DATA_BASE}/${path}`, { signal: AbortSignal.timeout(15_000) });
  if (!response.ok) {
    // A stale copy is better than an error while GitHub has a hiccup.
    if (hit) return hit.text;
    throw new UpstreamError(`${path}: upstream returned ${response.status}`);
  }
  const text = await response.text();
  cache.set(path, { at: now, text });
  return text;
}

export function clearCache(): void {
  cache.clear();
}
