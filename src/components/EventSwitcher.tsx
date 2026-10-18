import { useEffect, useRef, useState } from 'react';
import { useEvent, useStore } from '../state/store';
import { Chevron } from './Icons';

/** Top-bar event picker. Switching reloads with ?event=<id> so every panel starts from a clean state. */
export function EventSwitcher() {
  const event = useEvent();
  const catalog = useStore((s) => s.catalog);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const choose = (id: string) => {
    if (id === event.id) return setOpen(false);
    const url = new URL(location.href);
    url.searchParams.set('event', id);
    location.assign(url.toString());
  };

  return (
    <div className="switcher" ref={ref}>
      <button className="incident-select" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {event.name} <Chevron />
      </button>
      {open && (
        <ul className="switcher__menu" role="listbox" aria-label="Events">
          {catalog.map((c) => (
            <li key={c.id}>
              <button
                role="option"
                aria-selected={c.id === event.id}
                className={c.id === event.id ? 'is-current' : ''}
                disabled={!c.built}
                title={c.built ? undefined : 'Confirmed by review; data package not built yet'}
                onClick={() => choose(c.id)}
              >
                <span className="switcher__row">
                  <b>{c.name}</b>
                  <span className="switcher__date">{c.date}</span>
                  {c.status !== 'in-progress' && <span className="switcher__status">{c.built ? c.status : `${c.status} · not built`}</span>}
                </span>
                <span className="switcher__headline">{c.headline}</span>
              </button>
            </li>
          ))}
          <li className="switcher__foot">Grid scan: 641 candidates (2000–2026), ranked by population-weighted rain · top 25: 6 confirmed/known, 1 likely, 18 no flood report</li>
        </ul>
      )}
    </div>
  );
}
