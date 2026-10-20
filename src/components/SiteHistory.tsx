import { useMemo, useState } from 'react';
import type { CatalogFlood, CatalogSource, CatalogSummary, FloodType, SiteFlood, SiteRecord } from '../sites/types';
import { fmtOn } from './SitePanel';

/** The Floods card: every flood day the news reported for this place, merged with the floods we mapped in detail,
 *  plus the nearby, less certain matches and honest search coverage (Task 35). */

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
const yearOf = (iso: string) => +iso.slice(0, 4);

/** Non-rain flood types in plain words (Task 35 addendum); the rain type needs no tag. */
const TYPE_TAG: Partial<Record<FloodType, string>> = { riverine: 'river', coastal: 'sea' };

/** One row of the card: a strong flood day, a mapped flood, or both on the same date. */
interface FloodRow {
  date: string;
  flood: CatalogFlood | null;
  mapped: SiteFlood | null;
  eventId: string | null;
}

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
    <div className="year-strip" role="img" aria-label="Flooded years" title={summary.note}>
      {years.map((y) => {
        const s = strongBy.get(y);
        const n = nearbyBy.get(y);
        const cls = s ? ' year-strip__cell--strong' : n ? ' year-strip__cell--area' : '';
        const title = s
          ? `${y}: ${s.join(', ')} (flood day reported)`
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
  // One row per date: a strong flood day, a mapped flood, or both. Newest first, matching the timeline's dots.
  const rows = useMemo(() => {
    const byDate = new Map<string, FloodRow>();
    for (const f of strong) byDate.set(f.date, { date: f.date, flood: f, mapped: null, eventId: f.tier_a_event_id });
    for (const fl of site.floods) {
      const ex = byDate.get(fl.date);
      if (ex) {
        if (!ex.eventId) ex.eventId = fl.event_id;
        if (!ex.mapped) ex.mapped = fl;
      } else {
        byDate.set(fl.date, { date: fl.date, flood: null, mapped: fl, eventId: fl.event_id });
      }
    }
    return [...byDate.values()].sort((a, b) => b.date.localeCompare(a.date));
  }, [strong, site.floods]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showNearby, setShowNearby] = useState(false);
  // No catalog yet (older sites.json): nothing honest to say, so no card.
  if (!summary) return null;
  const nRain = strong.filter((f) => f.flood_type === 'pluvial').length;
  // Header counts every row, so it matches the bottom timeline's dots; the breakdown says where each came from.
  const nMappedOnly = rows.length - strong.length;
  const parts = [
    ...(nMappedOnly > 0 ? [`${strong.length} named in the news`] : []),
    ...(strong.length !== nRain ? [`${nRain} from rain`] : []),
    ...(nMappedOnly > 0 ? [`${nMappedOnly} mapped`] : []),
  ];
  const headCount = `${plural(rows.length, 'flood day')} ${nMappedOnly > 0 ? 'on record' : 'reported'}`;
  const breakdown = parts.length ? `${parts.join(', ')}.` : null;
  const years = [...summary.years_searched].sort((a, b) => a - b);
  const firstSearched = years[0];
  const replay = (row: FloodRow) =>
    row.eventId && (
      <button className="link" onClick={() => openEvent(row.eventId!)} disabled={opening !== null}>
        {opening === row.eventId ? 'Loading…' : 'Replay this flood →'}
      </button>
    );
  return (
    <section className="card" id="place-floods">
      <header className="card__head">
        <h3>Floods</h3>
        <span className="card__hint">{headCount}</span>
      </header>
      {breakdown && <p className="card__hint place-floods__breakdown">{breakdown[0].toUpperCase() + breakdown.slice(1)}</p>}
      <YearStrip summary={summary} strong={strong} nearby={nearby} />
      {rows.length === 0 && <p className="empty">No flood days reported in {summary.years_searched.length} years searched.</p>}
      {rows.length > 0 && (
        <ul className="site-floods">
          {rows.map((row) => {
            const f = row.flood;
            if (!f) {
              // A flood we mapped in detail on a day the catalog search did not match to this place.
              return (
                <li key={row.date}>
                  <span>
                    <span>
                      <b title={row.date}>{fmtOn(row.date)}</b>{' '}
                      <span className="cause-chip" title="A flood we mapped in detail, report by report.">mapped flood</span>
                      <small>
                        {row.mapped!.n_reports} report{row.mapped!.n_reports === 1 ? '' : 's'} · nearest {Math.round(row.mapped!.nearest_m)} m
                      </small>
                    </span>
                  </span>
                  {replay(row)}
                </li>
              );
            }
            const [first, ...rest] = f.sources;
            const isOpen = !!expanded[f.date];
            return (
              <li key={row.date}>
                <span>
                  <span>
                    <b title={f.date}>{fmtOn(f.date)}</b>
                    {f.flood_type !== 'pluvial' && (
                      <>
                        {' '}
                        <span className="cause-chip">{TYPE_TAG[f.flood_type] ?? f.flood_type}</span>
                      </>
                    )}{' '}
                    <small>{plural(f.n_outlets, 'news outlet')}</small>
                  </span>
                  <small>
                    {f.matched_areas.join(', ')} · {f.strength === 'name' ? 'named this place' : `a spot within ${Math.round(f.distance_m ?? 0)} m`}
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
                {replay(row)}
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
                    <b title={f.date}>{fmtOn(f.date)}</b>
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
        Searched news from {firstSearched}; earlier years not searched.
      </small>
    </section>
  );
}
