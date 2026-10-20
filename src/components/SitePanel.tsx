import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { loadEvent } from '../events/load';
import { SiteHistory } from './SiteHistory';
import { PlacesList } from './WatchList';
import { causeLabel, CAUSES } from '../lib/causes';
import { promiseStatus, type PromiseStatus, type PromiseUpdate } from '../lib/promises';
import { buildWatchList, type RainSummary, type WatchTest } from '../lib/watchList';
import type { CauseAttribution, CauseTag } from '../events/types';
import type { EvidenceStatus, SiteClaim, SitePromise, SiteRecord, WaybackImage } from '../sites/types';
import { ClampText } from './ClampText';
import { Chevron } from './Icons';
import { InfoTip } from './InfoTip';
import { useStore } from '../state/store';
import '../styles/place.css';

/** The place page (Task 35, docs/tasks/35-place-page.md). Screen question: does it flood, why, and did anyone fix
 *  it? The answer (At a glance) comes first; the evidence sits underneath in the same words as WORDS.md. */

/** On-screen words for the imagery check on each claim (docs/design/WORDS.md). */
export const EVIDENCE_LABEL: Record<EvidenceStatus, string> = {
  supports: 'Imagery agrees',
  weak: 'Imagery partly agrees',
  inconclusive: "Imagery can't tell",
  contradicts: 'Imagery disagrees',
  not_checked: 'Not checked yet',
  no_imagery_after: 'No imagery after the flood',
};

/** On-screen words for promise statuses (docs/design/WORDS.md). */
export const PROMISE_LABEL: Record<PromiseStatus, string> = {
  delivered: 'Done',
  in_progress: 'Work under way',
  stalled: 'Stalled',
  no_visible_work: 'No work seen',
  overdue: 'Overdue',
  unverifiable: "Can't check from imagery",
};

/** Tier → on-screen word (WORDS.md: 3/2/1/0 → High/Medium/Low/Lowest). Mirrors the list's badge words. */
export const PRIORITY: Record<number, string> = { 3: 'High', 2: 'Medium', 1: 'Low', 0: 'Lowest' };

/** Marker and line colours per priority tier, matching the badge colours in places.css. */
export const PRIORITY_RGB: Record<number, [number, number, number]> = {
  3: [163, 54, 31], // High, #a3361f
  2: [185, 123, 16], // Medium, #b97b10
  1: [93, 87, 78], // Low, #5d574e
  0: [154, 147, 133], // Lowest, #9a9385
};

/** buildWatchList needs the rain digest, but only its tie-breaks read it — the tiers and the three tests do not.
 *  Passing an empty digest gives the same signs as the list without a fetch, so the two can never disagree. */
export const EMPTY_RAIN_SUMMARY: RainSummary = { meta: { well_searched_years: [] }, sites: [] };

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "28 Jun 2026" — the prose date form (WORDS.md); ISO dates stay in hover notes. */
export const fmtOn = (iso: string) => `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
/** "Jun 2026", the month-year form for promise lines. */
const fmtMY = (iso: string) => `${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
const pad = (n: number) => (n < 10 ? '0' : '') + n;
const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
const year = (iso: string) => iso.slice(0, 4);
const asset = (f: string) => (f.startsWith('/') ? f : `/${f}`);

/** Findings in words: what an imagery check or an official claim showed (docs/design/WORDS.md wording). */
const FINDING_WORDS: Record<PromiseUpdate['finding'], string> = {
  done: 'done',
  work_seen: 'work seen',
  no_change: 'no work seen',
  claimed_done: 'said done',
  claimed_ongoing: 'said under way',
};

/** Worst first, mirroring watchList.ts. The tick comes from buildWatchList; this only picks which promise to quote. */
const PROMISE_SEVERITY: PromiseStatus[] = ['overdue', 'no_visible_work', 'stalled', 'in_progress', 'unverifiable', 'delivered'];

/** The drainage causes and attributions watchList.ts counts (its rule block, mirrored here for the quote only). */
const DRAINAGE_CAUSES: CauseTag[] = ['blocked_drainage', 'drainage_capacity', 'setback_encroachment'];
const PASSING_ATTRIBUTIONS: CauseAttribution[] = ['official', 'journalist'];
const SUPPORTING_EVIDENCE: EvidenceStatus[] = ['supports', 'weak'];

/** The claim the "Drains blamed" line quotes: same ranking as namedDrainage in watchList.ts. The tick itself
 *  always comes from buildWatchList, so the sign can never disagree with the list. */
function bestDrainageClaim(site: SiteRecord): SiteClaim | null {
  const candidates = (site.claims ?? []).filter((c) => DRAINAGE_CAUSES.includes(c.cause));
  if (candidates.length === 0) return null;
  const hits = candidates.filter(
    (c) => (c.attributed_by !== null && PASSING_ATTRIBUTIONS.includes(c.attributed_by)) || SUPPORTING_EVIDENCE.includes(c.evidence_status),
  );
  const rank = (c: SiteClaim) =>
    (c.attributed_by !== null && PASSING_ATTRIBUTIONS.includes(c.attributed_by) ? 0 : 1) * 2 +
    (c.evidence_status === 'supports' ? 0 : c.evidence_status === 'weak' ? 1 : 2);
  const pool = hits.length ? hits : candidates;
  return [...pool].sort((a, b) => rank(a) - rank(b) || (b.date ?? '').localeCompare(a.date ?? ''))[0] ?? null;
}

/** The promise the "Not fixed" line quotes: worst status first, as in watchList.ts and the places list. */
function worstFixPromise(
  site: SiteRecord,
  promises: Record<string, SitePromise>,
  asOf: Date,
  asOfIso: string,
): { promise: SitePromise; status: PromiseStatus } | null {
  const mine = (site.promise_ids ?? [])
    .map((id) => promises[id])
    .filter((p): p is SitePromise => !!p)
    .filter((p) => p.date_made <= asOfIso);
  const statuses = mine.map((p) => promiseStatus(p, asOf));
  const worst = PROMISE_SEVERITY.find((s) => statuses.includes(s));
  return worst ? { promise: mine[statuses.indexOf(worst)], status: worst } : null;
}

/** One "At a glance" line: the sign, the sentence, and a jump to the section it comes from. */
function GlanceLine({ test, text, target }: { test: WatchTest; text: string; target: string }) {
  return (
    <li>
      <button
        className="glance__line"
        onClick={() => document.getElementById(target)?.scrollIntoView({ block: 'start', behavior: 'smooth' })}
        title={`${test.label}: ${test.reason}`}
        aria-label={`${test.label}: ${text}. Jump to the evidence.`}
      >
        <span className={test.pass ? 'places__tick' : 'places__cross'} aria-hidden="true">
          {test.pass ? '✓' : '✗'}
        </span>
        <span className="glance__text">
          <b>{test.label}:</b> {text}
        </span>
        <span className="glance__go" aria-hidden="true">
          ↓
        </span>
      </button>
    </li>
  );
}

/** The three warning signs and the priority badge, computed with buildWatchList exactly as the places list does
 *  (same as-of default: today), so the two screens can never disagree. */
function AtAGlance({ site, promises }: { site: SiteRecord; promises: Record<string, SitePromise> }) {
  const asOf = useMemo(() => new Date(), []);
  const asOfIso = isoDay(asOf);
  const row = useMemo(() => buildWatchList([site], promises, EMPTY_RAIN_SUMMARY, asOf)[0], [site, promises, asOf]);
  const [tFloods, tDrains, tFix] = row.tests;

  // Floods often: the rain flood days the list counts (rule 1), with the addendum's "from rain" wording.
  const firstSearched = site.catalog_summary ? Math.min(...site.catalog_summary.years_searched) : 2014;
  const rainDays = (site.catalog_floods ?? []).filter(
    (f) => f.strength !== 'area' && f.flood_type === 'pluvial' && f.date <= asOfIso,
  );
  const lastRain = rainDays.reduce((a, f) => (f.date > a ? f.date : a), '');
  const floodsText = rainDays.length
    ? `${plural(rainDays.length, 'flood day')} from rain reported since ${firstSearched}; last ${fmtOn(lastRain)}`
    : `No flood days from rain reported since ${firstSearched}`;

  // Drains blamed: quote the best claim; when the sign fails, buildWatchList's reason already says why.
  const best = bestDrainageClaim(site);
  const drainsText =
    tDrains.pass && best
      ? `${best.who ?? (best.attributed_by ? `A ${best.attributed_by}` : 'An unnamed source')}: ${causeLabel(best.cause)} (${best.date ? year(best.date) : 'undated'}); ${EVIDENCE_LABEL[best.evidence_status]}`
      : tDrains.reason;

  // Not fixed: quote the promise in the worst state; the sign still comes from the test.
  const worst = tFix.pass ? worstFixPromise(site, promises, asOf, asOfIso) : null;
  const fixText = worst
    ? (() => {
        const last = worst.promise.updates[worst.promise.updates.length - 1];
        const finding = last ? `, ${FINDING_WORDS[last.finding]}` : '';
        return `${worst.promise.what} promised ${fmtMY(worst.promise.date_made)}: ${PROMISE_LABEL[worst.status].toLowerCase()}${finding}`;
      })()
    : tFix.reason;

  const prio = PRIORITY[row.tier] ?? 'Lowest';
  return (
    <section className="card" id="place-glance" aria-label="At a glance">
      <header className="card__head">
        <h3>At a glance</h3>
        <span className={`places__prio places__prio--${prio.toLowerCase()}`}>
          <span className="places__prio-shape" aria-hidden="true" />
          {prio}
          <InfoTip label={`${prio} priority`}>
            {`${prio} priority: ${row.tier} of 3 warning signs.`}
          </InfoTip>
        </span>
      </header>
      <ul className="glance">
        <GlanceLine test={tFloods} text={floodsText} target="place-floods" />
        <GlanceLine test={tDrains} text={drainsText} target="place-causes" />
        <GlanceLine test={tFix} text={fixText} target="place-promises" />
      </ul>
    </section>
  );
}

/** The verdict, clamped to three lines with a Read more toggle, dated and signed. */
function OurReading({ site }: { site: SiteRecord }) {
  const v = site.verdict;
  return (
    <section className="card" id="place-reading">
      <header className="card__head">
        <h3>Our reading</h3>
        {v?.stale && <span className="card__hint">numbers changed since review</span>}
      </header>
      {!v ? (
        <p className="empty">Not yet reviewed.</p>
      ) : (
        <>
          <span className="reading__strength">Evidence: {v.confidence}</span>
          <ClampText text={v.text} className="reading__text" />
          <small className="reading__meta">
            Reviewed {fmtOn(v.reviewed_at)} by {v.reviewed_by}
          </small>
        </>
      )}
    </section>
  );
}

/** A section that starts folded and opens on demand (the folding pattern from the places list). */
function Fold({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="fold">
      <button className="fold__toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <Chevron />
        {title}
      </button>
      {open && <div className="fold__body">{children}</div>}
    </div>
  );
}

/** Values by year as a tiny line chart, with flood years marked. */
function Sparkline({ byYear, floodYears, fmt }: { byYear: Record<string, number>; floodYears: string[]; fmt: (v: number) => string }) {
  const years = Object.keys(byYear).sort();
  if (years.length < 2) return <p className="empty">Not enough years.</p>;
  const vals = years.map((y) => byYear[y]);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const W = 300;
  const H = 54;
  const x = (i: number) => 6 + (i / (years.length - 1)) * (W - 12);
  const y = (v: number) => H - 14 - ((v - lo) / (hi - lo || 1)) * (H - 24);
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} width="100%">
      {years.map((yr, i) =>
        floodYears.includes(yr) ? <rect key={`f${yr}`} x={x(i) - 5} y={2} width={10} height={H - 14} className="spark__flood" /> : null,
      )}
      <polyline points={vals.map((v, i) => `${x(i)},${y(v)}`).join(' ')} className="spark__line" />
      {vals.map((v, i) => (
        <circle key={years[i]} cx={x(i)} cy={y(v)} r={2.4} className="spark__dot">
          <title>{`${years[i]}: ${fmt(v)}`}</title>
        </circle>
      ))}
      <text x={x(0)} y={H - 2} className="spark__label">{years[0]} · {fmt(vals[0])}</text>
      <text x={x(years.length - 1)} y={H - 2} textAnchor="end" className="spark__label">{years[years.length - 1]} · {fmt(vals[vals.length - 1])}</text>
    </svg>
  );
}

/** Two dated images, one on top of the other; the slider reveals "after" over "before". */
function BeforeAfter({ images }: { images: WaybackImage[] }) {
  // Drop coarse low-zoom fallbacks (e.g. the 1999 15 m mosaic): they can't show a drain.
  const usable = useMemo(
    () => images.filter((im) => (im.resolution_m ?? 0) <= 2).sort((a, b) => a.acq_date.localeCompare(b.acq_date)),
    [images],
  );
  const last = Math.max(0, usable.length - 1);
  // Default "before" = the latest earlier date with close-ups matching the latest image; otherwise the oldest.
  const pairedBefore = usable.slice(0, last).map((im) => !!im.detail_chips?.length).lastIndexOf(true);
  const [bi, setBi] = useState(usable[last]?.detail_chips?.length && pairedBefore >= 0 ? pairedBefore : 0);
  const [ai, setAi] = useState(last);
  const [split, setSplit] = useState(50);
  const [station, setStation] = useState('overview');
  if (usable.length < 2) return <p className="empty">Fewer than two dated images.</p>;
  const before = usable[bi];
  const after = usable[ai];
  // Close-ups can only be compared where both dates have one at the same station.
  const stations = (before.detail_chips ?? []).map((c) => c.station).filter((st) => after.detail_chips?.some((c) => c.station === st));
  const view = stations.includes(station) ? station : 'overview';
  const src = (im: WaybackImage) => {
    const chip = view === 'overview' ? im : im.detail_chips!.find((c) => c.station === view)!;
    return asset(chip.marked_file ?? chip.file);
  };
  return (
    <div className="ba">
      {stations.length > 0 && (
        <div className="segmented segmented--small">
          {['overview', ...stations].map((st) => (
            <button key={st} className={view === st ? 'is-active' : ''} onClick={() => setStation(st)}>
              {st === 'overview' ? 'Whole line' : `Close-up: ${st}`}
            </button>
          ))}
        </div>
      )}
      <div className="ba__frame">
        <img src={src(before)} alt={`Imagery ${fmtOn(before.acq_date)}`} />
        <img src={src(after)} alt={`Imagery ${fmtOn(after.acq_date)}`} className="ba__top" style={{ clipPath: `inset(0 0 0 ${split}%)` }} />
        <span className="ba__divider" style={{ left: `${split}%` }} />
      </div>
      <input type="range" min={0} max={100} value={split} onChange={(e) => setSplit(+e.target.value)} aria-label="Before/after split" />
      <div className="ba__dates">
        <label className="ba__end">
          Before <select value={bi} onChange={(e) => setBi(+e.target.value)} aria-label="Before date">
            {usable.map((im, i) => <option key={im.acq_date} value={i}>{im.acq_date}</option>)}
          </select>
        </label>
        <label className="ba__end">
          After <select value={ai} onChange={(e) => setAi(+e.target.value)} aria-label="After date">
            {usable.map((im, i) => <option key={im.acq_date} value={i}>{im.acq_date}</option>)}
          </select>
        </label>
      </div>
      <small className="causes__note">Esri World Imagery Wayback (acquisition dates) · Esri, Maxar, Earthstar Geographics</small>
    </div>
  );
}

function SiteDetail({ site, promises }: { site: SiteRecord; promises: Record<string, SitePromise> }) {
  const selectSite = useStore((s) => s.selectSite);
  const focusClaimId = useStore((s) => s.focusClaimId);
  // Arriving from a cause chip: bring that claim's row into view.
  useEffect(() => {
    if (focusClaimId) document.getElementById(`claim-${focusClaimId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [focusClaimId, site.site_id]);
  const [opening, setOpening] = useState<string | null>(null);
  const sitePromises = site.promise_ids.map((id) => promises[id]).filter(Boolean);
  const ch = site.change;
  // Years with a reported flood (mapped or a catalog flood day) shade the sparklines.
  const floodYears = useMemo(() => {
    const ys = new Set<string>();
    for (const f of site.floods) ys.add(year(f.date));
    for (const f of site.catalog_floods ?? []) if (f.strength !== 'area') ys.add(year(f.date));
    return [...ys];
  }, [site]);

  const openEvent = (id: string) => {
    setOpening(id);
    loadEvent(id)
      .then((e) => {
        useStore.getState().setEvent(e);
        useStore.getState().setMode('incident');
      })
      .catch(() => setOpening(null));
  };

  return (
    <>
      <header className="place-head">
        <button className="back" onClick={() => selectSite(null)}>← All places</button>
        <h2 className="site__name">{site.name}</h2>
        <p
          className="site__structure"
          title={`Location known to ${site.location_confidence} precision.${site.located_how ? ` ${site.located_how}` : ''}`}
        >
          {site.structure_name}
        </p>
      </header>

      <AtAGlance site={site} promises={promises} />

      <OurReading site={site} />

      <SiteHistory site={site} openEvent={openEvent} opening={opening} />

      <section className="card" id="place-promises">
        <header className="card__head">
          <h3>Promises</h3>
          <span className="card__hint">status from imagery only</span>
        </header>
        {sitePromises.length === 0 && <p className="empty">No promises on record for this place.</p>}
        <ul className="promises">
          {sitePromises.map((p) => {
            const last = p.updates[p.updates.length - 1];
            return (
              <li key={p.promise_id}>
                <span className={`status status--${p.status}`}>{PROMISE_LABEL[p.status]}</span>
                <b>{p.what}</b>
                <small>
                  {p.made_by}
                  {p.role ? `, ${p.role}` : ''} · {fmtOn(p.date_made)}
                </small>
                <small title={`Due date basis: ${p.due.basis}${p.due.note ? ` — ${p.due.note}` : ''}`}>
                  {p.due.date ? `Due: ${fmtOn(p.due.date)}` : 'No date given: we allow 12 months'}
                </small>
                {p.quote && (
                  <q>
                    <a href={p.url} target="_blank" rel="noreferrer">{p.quote}</a>
                  </q>
                )}
                {last && (
                  <small title={`Checked via ${last.kind}`}>
                    Last checked {fmtOn(last.date)}: {FINDING_WORDS[last.finding]}
                    {last.note && ` — ${last.note}`}
                  </small>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="card" id="place-causes">
        <header className="card__head">
          <h3>Who blamed what</h3>
          <span className="card__hint">each claim, who made it, and what satellite images show</span>
        </header>
        {site.claims.length === 0 && <p className="empty">No source named a cause here.</p>}
        <ol className="chain">
          {site.claims.map((c) => (
            <li key={c.claim_id} id={`claim-${c.claim_id}`} className={c.claim_id === focusClaimId ? 'is-focus' : undefined}>
              <span className={`cause-chip${CAUSES.find((x) => x.tag === c.cause)?.human ? ' cause-chip--human' : ''}`}>{causeLabel(c.cause)}</span>
              <span className="chain__who">
                {c.who ?? (c.attributed_by ? `A ${c.attributed_by}` : 'No one named')}
                {c.date && ` · ${fmtOn(c.date)}`}
              </span>
              {c.quote && (
                <q>
                  {c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.quote}</a> : c.quote}
                </q>
              )}
              <span className={`status status--ev-${c.evidence_status}`}>{EVIDENCE_LABEL[c.evidence_status]}</span>
              {c.status_note && <small>{c.status_note}</small>}
            </li>
          ))}
        </ol>
      </section>

      <section className="card" id="place-change">
        <header className="card__head">
          <h3>What changed on the ground</h3>
          {ch.stale && <span className="card__hint">numbers changed since review</span>}
        </header>
        {ch.summary && <p className="site__summary">{ch.summary}</p>}
        <h4 className="subhead">Then and now</h4>
        <BeforeAfter images={ch.wayback} />
        {(ch.s2_wet_season || ch.buildings_0_10m) && (
          <Fold title="Measurements">
            {ch.s2_wet_season && (
              <>
                <h4 className="subhead" title="Sentinel-2, wet-season images">Green cover in the rainy season</h4>
                <Sparkline byYear={ch.s2_wet_season.by_year} floodYears={floodYears} fmt={(v) => `${Math.round(v * 100)}%`} />
              </>
            )}
            {ch.buildings_0_10m && !ch.buildings_0_10m.excluded && (
              <>
                <h4 className="subhead" title="Google Open Buildings: share of the land within 10 m of the channel that is built on">
                  Building close by (within 10 m)
                </h4>
                <Sparkline byYear={ch.buildings_0_10m.by_year} floodYears={floodYears} fmt={(v) => `${(v * 100).toFixed(1)}%`} />
                {ch.buildings_0_10m.matched_pct != null && (
                  <p className="causes__note">
                    2016→2023 change higher than {Math.round(ch.buildings_0_10m.matched_pct)}% of {ch.buildings_0_10m.matched_n} similar city
                    channel stretches.
                  </p>
                )}
              </>
            )}
            {ch.buildings_0_10m?.excluded && <p className="causes__note">Open Buildings not used here: {ch.buildings_0_10m.excluded}.</p>}
            <small className="causes__note">Shaded columns: years with a reported flood.</small>
          </Fold>
        )}
      </section>
    </>
  );
}

export function SitePanel() {
  const loaded = useStore((s) => s.sites);
  const error = useStore((s) => s.sitesError);
  const selectedId = useStore((s) => s.selectedSiteId);
  const site = loaded?.sites.find((s) => s.site_id === selectedId);
  return (
    <aside className="right right--sites" id="place-panel">
      {!loaded && (
        <section className="card">
          <p className="empty">{error ? `Could not load sites: ${error}` : 'Loading sites…'}</p>
          {error && <button className="link" onClick={() => useStore.getState().setSites(null)}>Retry</button>}
        </section>
      )}
      {loaded && !site && <PlacesList sites={loaded.sites} promises={loaded.promises} />}
      {loaded && site && <SiteDetail key={site.site_id} site={site} promises={loaded.promises} />}
    </aside>
  );
}
