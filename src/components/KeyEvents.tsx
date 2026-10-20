import { useState } from 'react';
import type { KeyEventKind } from '../events/types';
import { fmtDateTime } from '../lib/time';
import { useEvent, useQuantTime, useStore } from '../state/store';
import { KIND_COLORS } from './Timeline';
import '../styles/flood.css';

function EventGlyph({ kind }: { kind: KeyEventKind }) {
  const c = KIND_COLORS[kind];
  switch (kind) {
    case 'satellite':
      return <svg viewBox="0 0 14 14" width="14" height="14"><rect x="4.5" y="4.5" width="5" height="5" fill={c} /><path d="M1 7h3M10 7h3" stroke={c} strokeWidth="2" /></svg>;
    case 'tide-high':
      return <svg viewBox="0 0 14 14" width="14" height="14"><path d="M1 9c2-2 4-2 6 0s4 2 6 0" stroke={c} strokeWidth="2" fill="none" /><path d="M7 1v5M5 3.5L7 1l2 2.5" stroke={c} strokeWidth="1.5" fill="none" /></svg>;
    case 'rain-onset':
      return <svg viewBox="0 0 14 14" width="14" height="14"><path d="M7 1C4.5 5 3 6.8 3 8.8a4 4 0 008 0C11 6.8 9.5 5 7 1z" fill={c} /></svg>;
    default:
      return <svg viewBox="0 0 14 14" width="14" height="14"><path d="M7 1l6 12H1z" fill={c} /></svg>;
  }
}

export function KeyEvents() {
  const event = useEvent();
  const t = useQuantTime();
  const t0 = useStore((s) => s.t0);
  const t1 = useStore((s) => s.t1);
  const selected = useStore((s) => s.selectedEventId);
  const { setTime, selectEvent, setPlaying } = useStore.getState();
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.matchMedia('(min-width: 721px)').matches);
  return (
    <section className={`events${open ? '' : ' is-folded'}`}>
      <header className="events__head">
        <h2>Key Events</h2>
        <button type="button" className="events__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          Key Events {open ? '▾' : '▸'}
        </button>
      </header>
      <ul>
        {event.keyEvents.map((ev) => {
          const inWindow = ev.t >= t0 && ev.t <= t1;
          return (
            <li key={ev.id}>
              <button
                className={`event ${selected === ev.id ? 'is-selected' : ''} ${ev.t > t ? 'is-future' : ''}`}
                disabled={!inWindow}
                title={inWindow ? `${ev.name}. Jump the replay to ${fmtDateTime(ev.t)}` : ev.name}
                onClick={() => {
                  setPlaying(false);
                  setTime(ev.t);
                  selectEvent(ev.id);
                }}
              >
                <EventGlyph kind={ev.kind} />
                <span className="event__name" title={ev.name}>
                  {ev.namePlain ?? ev.name}
                  {ev.timeConfidence !== 'exact' && <em> ({ev.timeConfidence === 'day' ? 'day only' : 'approx.'})</em>}
                </span>
                <span className="event__time">{fmtDateTime(ev.t)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
