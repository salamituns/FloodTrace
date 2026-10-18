import { useState } from 'react';
import { CAUSES, causeLabel } from '../lib/causes';
import { fmtDateTime } from '../lib/time';
import { useEvent } from '../state/store';
import { ConditionsCard } from './ConditionsCard';
import { EventOverview } from './EventOverview';
import { LayersPanel } from './LayersPanel';

const TABS = ['Layers', 'Evidence', 'Analysis', 'Notes'] as const;

function EvidenceList() {
  const event = useEvent();
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
              {e.props.causes.map((c) => (
                <span key={c} className={`cause-chip${CAUSES.find((x) => x.tag === c)?.human ? ' cause-chip--human' : ''}`}>
                  {causeLabel(c)}
                </span>
              ))}
            </span>
          )}
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
