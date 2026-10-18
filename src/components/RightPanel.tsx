import { useState } from 'react';
import { CAUSES, causeLabel } from '../lib/causes';
import { fmtDateTime } from '../lib/time';
import { useEventSiteLinks } from '../sites/links';
import { useEvent, useStore } from '../state/store';
import { ConditionsCard } from './ConditionsCard';
import { EventOverview } from './EventOverview';
import { LayersPanel } from './LayersPanel';
import { EVIDENCE_LABEL } from './SitePanel';

const TABS = ['Layers', 'Evidence', 'Analysis', 'Notes'] as const;

function EvidenceList() {
  const event = useEvent();
  const links = useEventSiteLinks();
  const openSite = useStore((s) => s.openSite);
  if (!event.evidence.length) return <p className="empty">No media evidence collected yet.</p>;
  const items = [...event.evidence].sort((a, b) => (a.t ?? Infinity) - (b.t ?? Infinity));
  return (
    <ul className="evidence-list">
      {items.map((e) => (
        <li key={e.props.id}>
          <a href={e.props.source_url} target="_blank" rel="noreferrer">
            <b>{e.props.location_name}</b>
          </a>
          <span>{e.props.claim}</span>
          {!!e.props.causes?.length && (
            <span className="cause-chips" title={e.props.cause_quote ?? undefined}>
              {e.props.causes.map((c) => {
                const cls = `cause-chip${CAUSES.find((x) => x.tag === c)?.human ? ' cause-chip--human' : ''}`;
                // A cause that became a site claim links to its row in that site's evidence chain.
                const hit = links.get(e.props.id)?.flatMap((l) => l.claims.map((cl) => ({ site: l.site, cl }))).find((x) => x.cl.cause === c);
                if (!hit) return <span key={c} className={cls}>{causeLabel(c)}</span>;
                return (
                  <button
                    key={c}
                    className={`${cls} cause-chip--link`}
                    title={`${hit.site.name}: ${EVIDENCE_LABEL[hit.cl.evidence_status]}. Open the evidence chain.`}
                    onClick={() => openSite(hit.site.site_id, hit.cl.claim_id)}
                  >
                    {causeLabel(c)} <span className={`ev-dot ev-dot--${hit.cl.evidence_status}`} /> →
                  </button>
                );
              })}
            </span>
          )}
          {links.get(e.props.id)?.map((l) => (
            <button key={l.site.site_id} className="link site-link" onClick={() => openSite(l.site.site_id)}>
              Part of site: {l.site.name} →
            </button>
          ))}
          <small>
            {e.props.publisher} · {e.t ? fmtDateTime(e.t) : 'time unknown'} · {e.props.location_confidence}
            {e.props.read_status === 'headline_only' && ' · headline only'}
          </small>
        </li>
      ))}
    </ul>
  );
}

export function RightPanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Layers');
  return (
    <aside className="right">
      <section className="card card--tabs">
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'is-active' : ''} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        {tab === 'Layers' && <LayersPanel />}
        {tab === 'Evidence' && <EvidenceList />}
        {(tab === 'Analysis' || tab === 'Notes') && <p className="empty">{tab} arrives in a later phase.</p>}
      </section>
      <ConditionsCard />
      <EventOverview />
    </aside>
  );
}
