import { useState } from 'react';
import { CAUSES, causeLabel } from '../lib/causes';
import { fmtDateTime } from '../lib/time';
import type { EvidenceStatus } from '../sites/types';
import { useEventSiteLinks } from '../sites/links';
import { useEvent, useQuantTime, useStore } from '../state/store';
import { ConditionsCard } from './ConditionsCard';
import { EventOverview } from './EventOverview';
import { LayersPanel } from './LayersPanel';
import '../styles/flood.css';

const EVIDENCE_LABEL: Record<EvidenceStatus, string> = {
  supports: 'Imagery agrees',
  weak: 'Imagery partly agrees',
  inconclusive: "Imagery can't tell",
  contradicts: 'Imagery disagrees',
  not_checked: 'Not checked yet',
  no_imagery_after: 'No imagery after the flood',
};

function EvidenceList() {
  const event = useEvent();
  const t = useQuantTime();
  const links = useEventSiteLinks();
  const openSite = useStore((s) => s.openSite);
  const [uptoNow, setUptoNow] = useState(false);
  const sorted = [...event.evidence].sort((a, b) => (a.t ?? Infinity) - (b.t ?? Infinity));
  const items = uptoNow ? sorted.filter((e) => e.t !== null && e.t <= t) : sorted;
  const n = event.evidence.length;

  return (
    <section className="card">
      <header className="news-head">
        <h2>News reports · {n}</h2>
        <label className="toggle">
          <input type="checkbox" checked={uptoNow} onChange={(e) => setUptoNow(e.target.checked)} />
          Only reports up to now
        </label>
      </header>
      {!n ? (
        <p className="empty">No news reports collected yet.</p>
      ) : (
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
                    const hit = links.get(e.props.id)?.flatMap((l) => l.claims.map((cl) => ({ site: l.site, cl }))).find((x) => x.cl.cause === c);
                    if (!hit) return <span key={c} className={cls}>{causeLabel(c)}</span>;
                    return (
                      <button
                        key={c}
                        className={`${cls} cause-chip--link`}
                        title={`${hit.site.name}: ${EVIDENCE_LABEL[hit.cl.evidence_status]}. Open who blamed what.`}
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
                  Part of place: {l.site.name} →
                </button>
              ))}
              <small>
                {e.props.publisher} · {e.t ? fmtDateTime(e.t) : 'time unknown'} · {e.props.location_confidence}
                {e.props.read_status === 'headline_only' && ' · headline only'}
              </small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function RightPanel() {
  return (
    <aside className="right">
      <EventOverview />
      <ConditionsCard />
      <EvidenceList />
      <LayersPanel />
    </aside>
  );
}
