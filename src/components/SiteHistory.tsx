import { useMemo, useState } from 'react';
import type { CatalogFlood, CatalogSource, CatalogSummary, SiteRecord } from '../sites/types';

/** "Flood history": the catalog flood days that matched this site, each with its sources, and honest search coverage. */

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
const yearOf = (iso: string) => +iso.slice(0, 4);

/** One cell per searched year: filled = a strong day, outlined = only nearby matches. Titles carry the dates. */
function YearStrip({ summary, strong, nearby }: { summary: CatalogSummary; strong: CatalogFlood[]; nearby: CatalogFlood[] }) {
  const datesBy = (list: CatalogFlood[]) => {
    const m = new Map<number, string[]>();
    for (const f of list) m.set(yearOf(f.date), [...(m.get(yearOf(f.date)) ?? []), f.date]);
    return m;
  };
  const strongBy = datesBy(strong);
  const nearbyBy = datesBy(nearby);
  const years = [...summary.years_searched].sort((a, b) => a - b);
  return (
    <div className="year-strip" role="img" aria-label="Flooded years">
      {years.map((y) => {
        const s = strongBy.get(y);
        const n = nearbyBy.get(y);
        const cls = s ? ' year-strip__cell--strong' : n ? ' year-strip__cell--area' : '';
        const title = s
          ? `${y}: ${s.join(', ')} (strong match)`
          : n
            ? `${y}: ${n.join(', ')} (nearby, less certain)`
            : `${y}: no matched flood day`;
        return (
          <span key={y} className={`year-strip__cell${cls}`} title={title}>
            {String(y).slice(2)}
          </span>
        );
      })}
    </div>
  );
}

function SourceLine({ src }: { src: CatalogSource }) {
  return (
    <small>
      <a className="link" href={src.url} target="_blank" rel="noreferrer">
        {src.publisher}
      </a>{' '}
      · <q>{src.quote}</q>
    </small>
  );
}

export function SiteHistory({
  site,
  openEvent,
  opening,
}: {
  site: SiteRecord;
  openEvent: (id: string) => void;
  opening: string | null;
}) {
  const summary = site.catalog_summary;
  const all = site.catalog_floods ?? [];
  const strong = useMemo(() => all.filter((f) => f.strength !== 'area').sort((a, b) => b.date.localeCompare(a.date)), [all]);
  const nearby = useMemo(() => all.filter((f) => f.strength === 'area').sort((a, b) => b.date.localeCompare(a.date)), [all]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showNearby, setShowNearby] = useState(false);
  // No catalog yet (older sites.json): nothing honest to say, so no card.
  if (!summary) return null;
  const years = [...summary.years_searched].sort((a, b) => a - b);
  const range = years.length === 0 ? '' : years.length === 1 ? `${years[0]}` : `${years[0]}–${years[years.length - 1]}`;
  return (
    <section className="card">
      <header className="card__head">
        <h3>Flood history</h3>
        <span className="card__hint">
          {plural(summary.n_days_strong, 'strong day')} in {summary.years_searched.length} years searched
        </span>
      </header>
      <YearStrip summary={summary} strong={strong} nearby={nearby} />
      {strong.length === 0 && (
        <p className="empty">No reported floods matched in {summary.years_searched.length} years searched.</p>
      )}
      {strong.length > 0 && (
        <ul className="site-floods">
          {strong.map((f) => {
            const [first, ...rest] = f.sources;
            const isOpen = !!expanded[f.date];
            return (
              <li key={f.date}>
                <span>
                  <span>
                    <b>{f.date}</b>
                    {f.flood_type !== 'pluvial' && <span className="cause-chip">{f.flood_type}</span>}{' '}
                    <small>
                      {f.n_outlets} outlet{f.n_outlets === 1 ? '' : 's'}
                    </small>
                  </span>
                  <small>
                    {f.matched_areas.join(', ')} · {f.strength === 'name' ? 'named' : `within ${Math.round(f.distance_m ?? 0)} m`}
                  </small>
                  {first && <SourceLine src={first} />}
                  {rest.length > 0 && (
                    <small>
                      <button
                        className="link"
                        onClick={() => setExpanded((e) => ({ ...e, [f.date]: !e[f.date] }))}
                        aria-expanded={isOpen}
                      >
                        {isOpen ? '− fewer' : `+${rest.length} more`}
                      </button>
                    </small>
                  )}
                  {isOpen && rest.map((s) => <SourceLine key={s.url} src={s} />)}
                </span>
                {f.tier_a_event_id && (
                  <button className="link" onClick={() => openEvent(f.tier_a_event_id!)} disabled={opening !== null}>
                    {opening === f.tier_a_event_id ? 'Opening…' : 'Open event →'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {nearby.length > 0 && (
        <div className="causes__note">
          <button className="link" onClick={() => setShowNearby(!showNearby)} aria-expanded={showNearby}>
            {nearby.length} nearby, less certain
          </button>
          {showNearby && (
            <ul className="site-floods">
              {nearby.map((f) => (
                <li key={f.date}>
                  <span>
                    <b>{f.date}</b>
                    <small>
                      {f.matched_areas.join(', ')} · {Math.round(f.distance_m ?? 0)} m away
                    </small>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <small className="causes__note">
        {summary.note}.
        {range && ` Searched ${range}; earlier years not searched.`}
      </small>
    </section>
  );
}
