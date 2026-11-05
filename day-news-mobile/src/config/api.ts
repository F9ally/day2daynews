// Static data published daily to Cloudflare Pages (see scripts/publish_site.sh):
//   data/index.json            -> { dates, months, audio: { daily?, monthly? } }
//   data/daily/YYYY-MM-DD.json -> { date, compiled, items }
//   data/monthly/YYYY-MM.json  -> { month, compiled, items }
//   audio/*.mp3                -> only the latest daily and monthly narration
export const DATA_BASE_URL = 'https://day2daynews.pages.dev';

export interface AudioEntry {
  key: string; // YYYY-MM-DD for daily, YYYY-MM for monthly
  file: string; // path relative to DATA_BASE_URL
}

export interface SiteIndex {
  dates: string[];
  months: string[];
  audio: { daily?: AudioEntry | null; monthly?: AudioEntry | null };
}

/** GET a JSON file from the site. Returns null on 404 (not published yet); throws on network errors. */
export async function fetchJson<T>(path: string): Promise<T | null> {
  const res = await fetch(`${DATA_BASE_URL}/${path}`, { headers: { 'Cache-Control': 'no-cache' } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
}

export const fetchIndex = () => fetchJson<SiteIndex>('data/index.json');
