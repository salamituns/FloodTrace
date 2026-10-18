import { useMemo, useState } from 'react';
import { loadEvent } from '../events/load';
import { causeLabel, CAUSES } from '../lib/causes';
import type { PromiseStatus } from '../lib/promises';
import { VERDICT_COLOR, verdictKey } from '../sites/geo';
import type { EvidenceStatus, SitePromise, SiteRecord, WaybackImage } from '../sites/types';
import { useStore } from '../state/store';

const EVIDENCE_LABEL: Record<EvidenceStatus, string> = {
  supports: 'Imagery supports',
  weak: 'Weak support',
  inconclusive: 'Inconclusive',
  contradicts: 'Imagery contradicts',
  not_checked: 'Not checked',
  no_imagery_after: 'No imagery after event',
};

export const PROMISE_LABEL: Record<PromiseStatus, string> = {
  delivered: 'Delivered',
  in_progress: 'In progress',
  stalled: 'Stalled',
  no_visible_work: 'No visible work',
  overdue: 'Overdue',
  unverifiable: 'Unverifiable',
};
/** Worst first: what the site list shows when a site has several promises. */
const PROMISE_SEVERITY: PromiseStatus[] = ['overdue', 'no_visible_work', 'stalled', 'in_progress', 'unverifiable', 'delivered'];

const rgb = (c: [number, number, number]) => `rgb(${c.join(',')})`;
const asset = (f: string) => (f.startsWith('/') ? f : `/${f}`);
const year = (iso: string) => iso.slice(0, 4);

function worstPromise(site: SiteRecord, promises: Record<string, SitePromise>): PromiseStatus | null {
  const st = site.promise_ids.map((id) => promises[id]?.status).filter(Boolean) as PromiseStatus[];
  return st.length ? PROMISE_SEVERITY.find((s) => st.includes(s)) ?? null : null;
}

function SiteList({ sites, promises }: { sites: SiteRecord[]; promises: Record<string, SitePromise> }) {
  const selectSite = useStore((s) => s.selectSite);
  const ranked = useMemo(
    () =>
      [...sites].sort(
        (a, b) => new Set(b.floods.map((f) => f.event_id)).size - new Set(a.floods.map((f) => f.event_id)).size || a.name.localeCompare(b.name),
      ),
    [sites],
  );
  return (
    <section className="card">
      <header className="card__head">
        <h3>Sites</h3>
        <span className="card__hint">{sites.length} places · most-flooded first</span>
      </header>
      <ul className="site-list">
        {ranked.map((s) => {
          const nEvents = new Set(s.floods.map((f) => f.event_id)).size;
          const worst = worstPromise(s, promises);
          return (
            <li key={s.site_id}>
              <button onClick={() => selectSite(s.site_id)}>
                <span className="site-dot" style={{ background: rgb(VERDICT_COLOR[verdictKey(s)]) }} />
                <span className="site-list__name">{s.name}</span>
                <span className="site-list__meta">
                  {nEvents} event{nEvents === 1 ? '' : 's'} · {s.claims.length} claim{s.claims.length === 1 ? '' : 's'}
                  {worst && <span className={`status status--${worst}`}>{PROMISE_LABEL[worst]}</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="causes__note">Dot = verdict strength (dark red strong → grey unreviewed). Label = worst promise status.</p>
    </section>
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
        <img src={src(before)} alt={`Imagery ${before.acq_date}`} />
        <img src={src(after)} alt={`Imagery ${after.acq_date}`} className="ba__top" style={{ clipPath: `inset(0 0 0 ${split}%)` }} />
        <span className="ba__divider" style={{ left: `${split}%` }} />
      </div>
      <input type="range" min={0} max={100} value={split} onChange={(e) => setSplit(+e.target.value)} aria-label="Before/after split" />
      <div className="ba__dates">
        <select value={bi} onChange={(e) => setBi(+e.target.value)} aria-label="Before date">
          {usable.map((im, i) => <option key={im.acq_date} value={i}>{im.acq_date}</option>)}
        </select>
        <span>← before · after →</span>
        <select value={ai} onChange={(e) => setAi(+e.target.value)} aria-label="After date">
          {usable.map((im, i) => <option key={im.acq_date} value={i}>{im.acq_date}</option>)}
        </select>
      </div>
      <small className="causes__note">Esri World Imagery Wayback (acquisition dates) · Esri, Maxar, Earthstar Geographics</small>
    </div>
  );
}

function SiteDetail({ site, promises }: { site: SiteRecord; promises: Record<string, SitePromise> }) {
  const selectSite = useStore((s) => s.selectSite);
  const catalog = useStore((s) => s.catalog);
  const [opening, setOpening] = useState<string | null>(null);
  const floodYears = [...new Set(site.floods.map((f) => year(f.date)))];
  const byEvent = useMemo(() => {
    const m = new Map<string, { date: string; n: number; nearest: number }>();
    for (const f of site.floods) m.set(f.event_id, { date: f.date, n: f.n_reports, nearest: f.nearest_m });
    return [...m.entries()].sort((a, b) => a[1].date.localeCompare(b[1].date));
  }, [site]);
  const sitePromises = site.promise_ids.map((id) => promises[id]).filter(Boolean);
  const ch = site.change;

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
      <section className="card">
        <button className="back" onClick={() => selectSite(null)}>← All sites</button>
        <h3 className="site__name">{site.name}</h3>
        <p className="site__structure">
          {site.structure_name} · <span className="card__hint">location: {site.location_confidence}</span>
        </p>
        {site.verdict ? (
          <p className="verdict" style={{ borderColor: rgb(VERDICT_COLOR[site.verdict.confidence]) }}>
            <b>{site.verdict.confidence[0].toUpperCase() + site.verdict.confidence.slice(1)} evidence.</b> {site.verdict.text}
            {site.verdict.stale && <em> (numbers changed since review)</em>}
            <small>Reviewed {site.verdict.reviewed_at} by {site.verdict.reviewed_by}</small>
          </p>
        ) : (
          <p className="verdict verdict--none">Not yet reviewed.</p>
        )}
      </section>

      <section className="card">
        <header className="card__head">
          <h3>Evidence chain</h3>
          <span className="card__hint">claim → structure → change → flood → status</span>
        </header>
        {site.claims.length === 0 && <p className="empty">No source named a cause here.</p>}
        <ol className="chain">
          {site.claims.map((c) => (
            <li key={c.claim_id}>
              <span className={`cause-chip${CAUSES.find((x) => x.tag === c.cause)?.human ? ' cause-chip--human' : ''}`}>{causeLabel(c.cause)}</span>
              <span className="chain__who">
                {c.who ?? c.attributed_by ?? 'unattributed'}
                {c.date && ` · ${c.date}`}
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

      <section className="card">
        <header className="card__head">
          <h3>Floods here</h3>
          <span className="card__hint">{byEvent.length} event{byEvent.length === 1 ? '' : 's'}</span>
        </header>
        <ul className="site-floods">
          {byEvent.map(([id, f]) => (
            <li key={id}>
              <span>
                <b>{catalog.find((c) => c.id === id)?.name ?? id}</b>
                <small>{f.date} · {f.n} report{f.n === 1 ? '' : 's'} · nearest {Math.round(f.nearest)} m</small>
              </span>
              <button className="link" onClick={() => openEvent(id)} disabled={opening !== null}>
                {opening === id ? 'Opening…' : 'Open event →'}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <header className="card__head">
          <h3>What changed</h3>
          {ch.stale && <span className="card__hint">numbers changed since review</span>}
        </header>
        {ch.summary && <p className="site__summary">{ch.summary}</p>}
        <BeforeAfter images={ch.wayback} />
        {ch.s2_wet_season && (
          <>
            <h4 className="subhead">Vegetation, wet season (Sentinel-2)</h4>
            <Sparkline byYear={ch.s2_wet_season.by_year} floodYears={floodYears} fmt={(v) => `${Math.round(v * 100)}%`} />
          </>
        )}
        {ch.buildings_0_10m && !ch.buildings_0_10m.excluded && (
          <>
            <h4 className="subhead">Built within 10 m of the channel (Open Buildings)</h4>
            <Sparkline byYear={ch.buildings_0_10m.by_year} floodYears={floodYears} fmt={(v) => `${(v * 100).toFixed(1)}%`} />
            {ch.buildings_0_10m.matched_pct != null && (
              <p className="causes__note">
                2016→2023 change higher than {Math.round(ch.buildings_0_10m.matched_pct)}% of {ch.buildings_0_10m.matched_n} similar city channel
                stretches. Shaded = flood years.
              </p>
            )}
          </>
        )}
        {ch.buildings_0_10m?.excluded && <p className="causes__note">Open Buildings not used here: {ch.buildings_0_10m.excluded}.</p>}
      </section>

      <section className="card">
        <header className="card__head">
          <h3>Promises</h3>
          <span className="card__hint">status from imagery only</span>
        </header>
        {sitePromises.length === 0 && <p className="empty">No official commitment found for this site yet.</p>}
        <ul className="promises">
          {sitePromises.map((p) => {
            const last = p.updates[p.updates.length - 1];
            return (
              <li key={p.promise_id}>
                <span className={`status status--${p.status}`}>{PROMISE_LABEL[p.status]}</span>
                <b>{p.what}</b>
                <small>
                  {p.made_by} · {p.date_made}
                  {p.due.date ? ` · due ${p.due.date} (${p.due.basis})` : ' · no due date (12-month grace)'}
                </small>
                {p.quote && (
                  <q>
                    <a href={p.url} target="_blank" rel="noreferrer">{p.quote}</a>
                  </q>
                )}
                {last && (
                  <small>
                    Latest: {last.date} · {last.kind} · {last.finding.replace(/_/g, ' ')}
                    {last.note && ` (${last.note})`}
                  </small>
                )}
              </li>
            );
          })}
        </ul>
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
    <aside className="right right--sites">
      {!loaded && <section className="card"><p className="empty">{error ? `Could not load sites: ${error}` : 'Loading sites…'}</p></section>}
      {loaded && !site && <SiteList sites={loaded.sites} promises={loaded.promises} />}
      {loaded && site && <SiteDetail site={site} promises={loaded.promises} />}
    </aside>
  );
}
