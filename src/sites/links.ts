import { useMemo } from 'react';
import { useStore } from '../state/store';
import type { SiteClaim, SiteRecord } from './types';

export interface EvidenceSiteLink {
  site: SiteRecord;
  /** The site's claims that rest on this report (one per cause the source named). */
  claims: SiteClaim[];
}

/**
 * Which site each of an event's reports belongs to, and the site claims it supports. A report belongs to a site when
 * build_sites.py put it in that site's floods (within the flood radius) or made a claim from it.
 */
export function siteLinksForEvent(sites: SiteRecord[], eventId: string): Map<string, EvidenceSiteLink[]> {
  const out = new Map<string, EvidenceSiteLink[]>();
  const add = (evId: string, site: SiteRecord) => {
    const list = out.get(evId) ?? [];
    if (!list.some((l) => l.site.site_id === site.site_id)) {
      const prefix = `${site.site_id}-${eventId}-`;
      list.push({ site, claims: site.claims.filter((c) => c.claim_id === `${prefix}${evId}`) });
      out.set(evId, list);
    }
  };
  for (const site of sites) {
    for (const f of site.floods) if (f.event_id === eventId) for (const id of f.evidence_ids) add(id, site);
    for (const c of site.claims) if (c.event_id === eventId) add(c.claim_id.slice(`${site.site_id}-${eventId}-`.length), site);
  }
  return out;
}

/** Site links for the current event; empty until sites.json has loaded. */
export function useEventSiteLinks(): Map<string, EvidenceSiteLink[]> {
  const sites = useStore((s) => s.sites?.sites);
  const eventId = useStore((s) => s.event?.id);
  return useMemo(() => (sites && eventId ? siteLinksForEvent(sites, eventId) : new Map()), [sites, eventId]);
}
