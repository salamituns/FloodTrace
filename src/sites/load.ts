import { promiseStatus, type OfficialPromise } from '../lib/promises';
import type { LoadedSites, SitePromise, SiteRecord } from './types';

/** Loads the site registry and promises. Statuses are computed here from evidence, never read from the file. */
export async function loadSites(today = new Date()): Promise<LoadedSites> {
  const res = await fetch('/events/sites.json');
  if (!res.ok) throw new Error(`sites.json: HTTP ${res.status}`);
  const { sites } = (await res.json()) as { sites: SiteRecord[] };

  const promises: Record<string, SitePromise> = {};
  const pres = await fetch('/events/promises.json');
  if (pres.ok) {
    const { promises: list } = (await pres.json()) as { promises: OfficialPromise[] };
    for (const p of list) promises[p.promise_id] = { ...p, updates: p.updates ?? [], status: promiseStatus(p, today) };
  }
  return { sites, promises };
}
