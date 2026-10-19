import { promiseStatus, type OfficialPromise } from '../lib/promises';
import type { RainSummary } from '../lib/watchList';
import type { LoadedSites, SitePromise, SiteRecord } from './types';

/**
 * Fetches JSON, retrying with backoff. The dev server can briefly answer with its HTML fallback while the pipeline
 * rewrites a file, so a parse failure is retried like a network error.
 */
async function fetchJson<T>(url: string, tries = 3): Promise<T> {
  for (let i = 1; ; i++) {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
      return (await res.json()) as T;
    } catch (err) {
      if (i >= tries) throw err;
      await new Promise((r) => setTimeout(r, 500 * 2 ** (i - 1)));
    }
  }
}

/** Loads the site registry and promises. Statuses are computed here from evidence, never read from the file. */
export async function loadSites(today = new Date()): Promise<LoadedSites> {
  const { sites } = await fetchJson<{ sites: SiteRecord[] }>('/events/sites.json');

  const promises: Record<string, SitePromise> = {};
  // Promises are optional: a site page still works without them.
  const list = await fetchJson<{ promises: OfficialPromise[] }>('/events/promises.json')
    .then((d) => d.promises)
    .catch(() => [] as OfficialPromise[]);
  for (const p of list) promises[p.promise_id] = { ...p, updates: p.updates ?? [], status: promiseStatus(p, today) };
  return { sites, promises };
}

/** The slim per-site digest of the rain replay (pipeline/storm_replay.py, Task 32) that the watch list ranks on. */
export function loadRainSummary(): Promise<RainSummary> {
  return fetchJson<RainSummary>('/events/site_rain_summary.json');
}
