import { useEffect, useMemo, useRef, useState } from 'react';
import type { PromiseStatus } from '../lib/promises';
import { useStore } from '../state/store';
import { PROMISE_LABEL } from './SitePanel';

const START = Date.UTC(2011, 0, 1);
const ROW = 26;
const LEFT = 110;
const ROWS = ['Floods', 'Promises', 'Imagery', 'Built ≤10 m'] as const;

const STATUS_FILL: Record<PromiseStatus, string> = {
  delivered: '#3f8f5a',
  in_progress: '#3d7fc4',
  stalled: '#c9852f',
  no_visible_work: '#b0442e',
  overdue: '#8e2a1a',
  unverifiable: '#9a9389',
};

/**
 * Years on one axis for the selected site: floods, promises (made → due) and imagery dates, plus building
 * growth beside the channel. With no site selected, every site's floods are shown, so recurring years stand out.
 */
/** Width of an element in CSS pixels, so the SVG can draw at 1:1 instead of stretching. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(1000);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(400, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export function SiteTimeline() {
  const [boxRef, W] = useWidth<HTMLDivElement>();
  const loaded = useStore((s) => s.sites);
  const selectedId = useStore((s) => s.selectedSiteId);
  const end = useMemo(() => Date.UTC(new Date().getUTCFullYear() + 1, 0, 1), []);
  const x = (iso: string) => LEFT + ((Date.parse(iso) - START) / (end - START)) * (W - LEFT - 10);
  const years = useMemo(() => {
    const out: number[] = [];
    for (let y = 2011; y <= new Date(end).getUTCFullYear(); y++) out.push(y);
    return out;
  }, [end]);

  if (!loaded) return <div className="site-tl empty" ref={boxRef}>Loading sites…</div>;
  const site = loaded.sites.find((s) => s.site_id === selectedId);
  const sites = site ? [site] : loaded.sites;
  const H = 18 + ROWS.length * ROW;
  const rowY = (i: number) => 18 + i * ROW + ROW / 2;

  const floods = new Map<string, { date: string; n: number }>();
  for (const s of sites) for (const f of s.floods) floods.set(f.event_id, { date: f.date, n: (floods.get(f.event_id)?.n ?? 0) + f.n_reports });
  const promises = site ? site.promise_ids.map((id) => loaded.promises[id]).filter(Boolean) : [];
  const built = site?.change.buildings_0_10m && !site.change.buildings_0_10m.excluded ? site.change.buildings_0_10m.by_year : null;
  const builtYears = built ? Object.keys(built).sort() : [];
  const bMax = built ? Math.max(...Object.values(built), 0.0001) : 1;

  return (
    <div className="site-tl" ref={boxRef}>
      <div className="site-tl__head">
        <b>{site ? site.name : 'All sites'}</b>
        <span className="card__hint">
          {site ? 'floods, promises and change on one axis' : `${floods.size} flood events across ${loaded.sites.length} sites; select a site for its promises and change`}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="site-tl__svg">
        {years.map((y) => (
          <g key={y}>
            <line x1={x(`${y}-01-01`)} x2={x(`${y}-01-01`)} y1={12} y2={H} className="site-tl__grid" />
            <text x={x(`${y}-07-01`)} y={10} textAnchor="middle" className="site-tl__year">{y}</text>
          </g>
        ))}
        {ROWS.map((r, i) => (
          <text key={r} x={8} y={rowY(i) + 4} className="site-tl__row">{r}</text>
        ))}

        {[...floods.entries()].map(([id, f]) => (
          <g key={id}>
            <circle cx={x(f.date)} cy={rowY(0)} r={Math.min(9, 3 + Math.sqrt(f.n))} className="site-tl__flood" />
            <title>{`${id}: ${f.n} report${f.n === 1 ? '' : 's'}`}</title>
          </g>
        ))}

        {promises.map((p, i) => {
          const made = x(p.date_made);
          const due = p.due.date ? x(p.due.date) : x(new Date(Date.parse(p.date_made) + 365 * 864e5).toISOString());
          const y = rowY(1) + ((i % 3) - 1) * 6;
          return (
            <g key={p.promise_id}>
              <line x1={made} x2={due} y1={y} y2={y} stroke={STATUS_FILL[p.status]} strokeWidth={2} strokeDasharray={p.due.date ? undefined : '3 2'} />
              <rect x={made - 4} y={y - 4} width={8} height={8} transform={`rotate(45 ${made} ${y})`} fill={STATUS_FILL[p.status]} />
              <title>{`${p.what} · ${PROMISE_LABEL[p.status]} · made ${p.date_made}${p.due.date ? `, due ${p.due.date}` : ', 12-month grace'}`}</title>
            </g>
          );
        })}

        {site?.change.wayback
          .filter((im) => (im.resolution_m ?? 0) <= 2)
          .map((im) => (
            <line key={im.acq_date} x1={x(im.acq_date)} x2={x(im.acq_date)} y1={rowY(2) - 7} y2={rowY(2) + 7} className="site-tl__img">
              <title>{`Imagery ${im.acq_date}`}</title>
            </line>
          ))}

        {built &&
          builtYears.map((yr) => {
            const h = (built[yr] / bMax) * (ROW - 8);
            return (
              <rect key={yr} x={x(`${yr}-03-01`)} y={rowY(3) + (ROW - 8) / 2 - h} width={(W - LEFT) / years.length * 0.6} height={h} className="site-tl__built">
                <title>{`${yr}: ${(built[yr] * 100).toFixed(1)}% built within 10 m`}</title>
              </rect>
            );
          })}
      </svg>
    </div>
  );
}
