import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react';
import { promiseStatus, type PromiseStatus } from '../lib/promises';
import { buildWatchList, type RainSummary, type WatchTest } from '../lib/watchList';
import { loadRainSummary } from '../sites/load';
import type { SitePromise, SiteRecord } from '../sites/types';
import { useStore } from '../state/store';
import { Chevron } from './Icons';
import { InfoTip } from './InfoTip';
import '../styles/places.css';

/** The one list of places (Task 33): the old watch-list card and the old Sites card merged into a single card
 *  titled with the mode's own words. Ranking, tie-breaks and reason strings come from lib/watchList.ts. */

/** The pre-season anchor (the old default): 1 March of the current year if today is past it, else of last year. */
function preSeason(today: Date): string {
  const march = (y: number) => `${y}-03-01`;
  return today >= new Date(`${march(today.getFullYear())}T00:00:00`) ? march(today.getFullYear()) : march(today.getFullYear() - 1);
}

const pad = (n: number) => (n < 10 ? '0' : '') + n;
/** Local day as an ISO date. The ranking is "as of today" by default (docs/design/WORDS.md). */
const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "1 Mar 2026" from an ISO date — the prose form (WORDS.md); ISO dates stay in hover notes. */
const fmtOn = (iso: string) => `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;

/** On-screen words for promise statuses (docs/design/WORDS.md). */
const PROMISE_LABEL: Record<PromiseStatus, string> = {
  delivered: 'Done',
  in_progress: 'Work under way',
  stalled: 'Stalled',
  no_visible_work: 'No work seen',
  overdue: 'Overdue',
  unverifiable: "Can't check from imagery",
};

/** Priority word for the number of warning signs (WORDS.md: 3/2/1/0 → High/Medium/Low/Lowest). */
const PRIORITY: Record<number, string> = { 3: 'High', 2: 'Medium', 1: 'Low', 0: 'Lowest' };

/** Hover notes for the three sign columns (docs/design/WORDS.md). */
const TEST_NOTE: Record<WatchTest['key'], string> = {
  repeated_flooding: 'At least 2 flood days reported, one in the last 3 rainy seasons.',
  named_drainage_failure: 'An official or reporter blamed the drains, or imagery agrees.',
  no_visible_fix: 'No promised fix is visibly done.',
};

/** Worst first, mirroring the order watchList.ts uses in its reason strings. */
const PROMISE_SEVERITY: PromiseStatus[] = ['overdue', 'no_visible_work', 'stalled', 'in_progress', 'unverifiable', 'delivered'];

/** Flood days the news reported for this place or a spot near it, on or before the as-of date — the same filter
 *  rule 1 in watchList.ts uses, so the second line and the tick always agree. */
function floodDayInfo(site: SiteRecord, asOfIso: string): { count: number; last: string | null } {
  const days = (site.catalog_floods ?? []).filter(
    (f) => (f.strength === 'name' || f.strength === 'near') && f.flood_type === 'pluvial' && f.date <= asOfIso,
  );
  let last: string | null = null;
  for (const f of days) if (!last || f.date > last) last = f.date;
  return { count: days.length, last };
}

/** The promise in the worst state as of the chosen date, or null when nothing had been promised by then. */
function worstPromise(site: SiteRecord, promises: Record<string, SitePromise>, asOf: Date, asOfIso: string): PromiseStatus | null {
  const statuses = site.promise_ids
    .map((id) => promises[id])
    .filter((p): p is SitePromise => !!p)
    .filter((p) => p.date_made <= asOfIso)
    .map((p) => promiseStatus(p, asOf));
  return statuses.length ? (PROMISE_SEVERITY.find((s) => statuses.includes(s)) ?? null) : null;
}

/** The second line of a row: "N flood days reported · last 28 Jun 2026 · promise Overdue", with any part that
 *  has no data left out. */
function PlaceMeta({
  site,
  promises,
  asOf,
  asOfIso,
}: {
  site: SiteRecord;
  promises: Record<string, SitePromise>;
  asOf: Date;
  asOfIso: string;
}) {
  const { count, last } = floodDayInfo(site, asOfIso);
  const worst = worstPromise(site, promises, asOf, asOfIso);
  const bits: ReactNode[] = [];
  if (count > 0) bits.push(<span key="n">{count} flood day{count === 1 ? '' : 's'} reported</span>);
  if (last) bits.push(<span key="l">last {fmtOn(last)}</span>);
  if (worst)
    bits.push(
      <span key="p" className="places__promise">
        promise <span className={`status status--${worst}`}>{PROMISE_LABEL[worst]}</span>
      </span>,
    );
  if (bits.length === 0) return null;
  // Inline flow, not flex: the parts sit on one line where they fit and wrap naturally otherwise. The NBSP keeps
  // each "·" glued to the part before it, and the promise unit is nowrap, so "promise" is never alone on a line.
  return (
    <span className="places__meta">
      {bits.map((b, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="places__sep">{' · '}</span>}
          {b}
        </Fragment>
      ))}
    </span>
  );
}

export function PlacesList({ sites, promises }: { sites: SiteRecord[]; promises: Record<string, SitePromise> }) {
  const selectSite = useStore((s) => s.selectSite);
  const [summary, setSummary] = useState<RainSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asOf, setAsOf] = useState(() => isoDay(new Date()));
  const [editingAsOf, setEditingAsOf] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sort, setSort] = useState<'priority' | 'days' | 'az'>('priority');

  useEffect(() => {
    loadRainSummary()
      .then(setSummary)
      .catch((err: unknown) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!editingAsOf) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setEditingAsOf(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [editingAsOf]);

  const asOfDate = useMemo(() => new Date(`${asOf}T00:00:00`), [asOf]);
  const ranked = useMemo(
    () => (summary ? buildWatchList(sites, promises, summary, asOfDate) : []),
    [sites, promises, summary, asOfDate],
  );
  const siteById = useMemo(() => new Map(sites.map((s) => [s.site_id, s])), [sites]);

  const rows = useMemo(() => {
    if (ranked.length === 0) return ranked;
    // Priority: exactly the order buildWatchList returns (tier descending, then its tie-breaks).
    if (sort === 'priority') return ranked;
    if (sort === 'az') return [...ranked].sort((a, b) => a.name.localeCompare(b.name));
    // "Most flood days" reproduces the old site list order: most reported flood days, then most floods, then A–Z.
    const nEvents = (s: SiteRecord) => new Set(s.floods.map((f) => f.event_id)).size;
    return [...ranked].sort((a, b) => {
      const A = siteById.get(a.site_id)!;
      const B = siteById.get(b.site_id)!;
      return (B.catalog_summary?.n_days_strong ?? 0) - (A.catalog_summary?.n_days_strong ?? 0) || nEvents(B) - nEvents(A) || a.name.localeCompare(b.name);
    });
  }, [ranked, sort, siteById]);

  // The answer line: which places show all three warning signs.
  const allThree = ranked.filter((r) => r.tier === 3);
  let answer: string;
  if (allThree.length === 0) {
    answer = 'No place shows all three warning signs.';
  } else {
    const names = allThree.map((r) => r.name);
    const list = names.length === 1 ? names[0] : names.length === 2 ? names.join(' and ') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
    answer = `${allThree.length} place${allThree.length === 1 ? '' : 's'} show${allThree.length === 1 ? 's' : ''} all three warning signs: ${list}.`;
  }

  return (
    <section className="card">
      <header className="card__head">
        <h2>Places that flood</h2>
        <span className="card__hint">{sites.length} places</span>
      </header>
      {!summary && !error && <p className="empty">Loading the rain record…</p>}
      {error && (
        <p className="empty">
          Could not load the rain record: {error}{' '}
          <button className="link" onClick={() => useStore.getState().setSites(null)}>
            Retry
          </button>
        </p>
      )}
      {summary && rows.length === 0 && <p className="empty">No places on record yet.</p>}
      {summary && rows.length > 0 && (
        <>
          <p className="places__answer">{answer}</p>
          <p className="places__asof">
            Ranked as of{' '}
            {editingAsOf ? (
              <>
                <input
                  type="date"
                  value={asOf}
                  onChange={(e) => {
                    if (e.target.value) setAsOf(e.target.value);
                  }}
                  aria-label="Ranked as-of date"
                  title="The list as it would have looked on this date."
                />
                <span className="places__sep">·</span>
                <button
                  className="link"
                  onClick={() => setAsOf(preSeason(new Date()))}
                  title="The list as it would have looked on 1 March: the pre-season list."
                >
                  1 March (pre-season)
                </button>
                <span className="places__sep">·</span>
                <button className="link" onClick={() => setEditingAsOf(false)}>
                  hide
                </button>
              </>
            ) : (
              <>
                <span>{asOf === isoDay(new Date()) ? 'today' : fmtOn(asOf)}</span>
                <span className="places__sep">·</span>
                <button className="link" onClick={() => setEditingAsOf(true)}>
                  change
                </button>
              </>
            )}
          </p>
          <div className="places__sort" role="group" aria-label="Sort places by">
            <span className="places__sortlabel">Sort:</span>
            <button className={sort === 'priority' ? 'is-active' : ''} aria-pressed={sort === 'priority'} onClick={() => setSort('priority')}>
              Priority
            </button>
            <button className={sort === 'days' ? 'is-active' : ''} aria-pressed={sort === 'days'} onClick={() => setSort('days')}>
              Most flood days
            </button>
            <button className={sort === 'az' ? 'is-active' : ''} aria-pressed={sort === 'az'} onClick={() => setSort('az')}>
              A–Z
            </button>
          </div>
          <div className="places__cols">
            <span className="places__col places__col--place">
              Place
              <InfoTip label="What priority means">
                High, Medium, Low or Lowest: how many of the three warning signs are present (out of 3).
              </InfoTip>
            </span>
            <span className="places__col">
              Floods often
              <InfoTip label="What Floods often means">{TEST_NOTE.repeated_flooding}</InfoTip>
            </span>
            <span className="places__col">
              Drains blamed
              <InfoTip label="What Drains blamed means">{TEST_NOTE.named_drainage_failure}</InfoTip>
            </span>
            <span className="places__col">
              Not fixed
              <InfoTip label="What Not fixed means">{TEST_NOTE.no_visible_fix}</InfoTip>
            </span>
            <span />
          </div>
          <ul className="places">
            {rows.map((r) => {
              const site = siteById.get(r.site_id);
              const isOpen = expanded === r.site_id;
              const prio = PRIORITY[r.tier] ?? 'Lowest';
              return (
                <li key={r.site_id}>
                  <div className="places__row">
                    <button type="button" className="places__open" onClick={() => selectSite(r.site_id)}>
                      <span className="places__main">
                        <span className="places__name">
                          <span className={`places__prio places__prio--${prio.toLowerCase()}`} title={`${prio} priority: ${r.tier} of 3 warning signs`}>
                            <span className="places__prio-shape" aria-hidden="true" />
                            {prio}
                          </span>
                          <span className="places__nametext">{r.name}</span>
                        </span>
                        {site && <PlaceMeta site={site} promises={promises} asOf={asOfDate} asOfIso={asOf} />}
                      </span>
                      {r.tests.map((t) => (
                        <span
                          key={t.key}
                          className={t.pass ? 'places__tick' : 'places__cross'}
                          role="img"
                          aria-label={`${t.label}: ${t.pass ? 'yes' : 'no'}`}
                          title={`${t.label}: ${t.reason}`}
                        >
                          {t.pass ? '✓' : '✗'}
                        </span>
                      ))}
                    </button>
                    <button
                      type="button"
                      className="places__why"
                      onClick={() => setExpanded(isOpen ? null : r.site_id)}
                      aria-expanded={isOpen}
                      aria-label={`Reasons for ${r.name}`}
                    >
                      <Chevron />
                    </button>
                  </div>
                  {isOpen && (
                    <ul className="places__reasons">
                      {r.tests.map((t) => (
                        <li key={t.key}>
                          <b>{t.label}:</b> {t.reason}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
      <p className="card__foot">Ranks places by what's on record, not by forecast. A place with no reports can still flood.</p>
    </section>
  );
}
