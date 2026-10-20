import { useEffect, useMemo, useRef, useState } from 'react';
import type { PromiseStatus } from '../lib/promises';
import { useStore } from '../state/store';
import { fmtOn, PROMISE_LABEL } from './SitePanel';
import '../styles/place.css';

/** The news search started in 2014 (Task 35); earlier years stay visible only when a mapped flood needs them. */
const NEWS_START = 2014;
const ROW = 26;
const LEFT = 110;
const ROWS = ['Floods', 'Promises', 'Satellite images', 'Building close by'] as const;

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

const STATUS_FILL: Record<PromiseStatus, string> = {
  delivered: '#3f8f5a',
  in_progress: '#3d7fc4',
  stalled: '#c9852f',
  no_visible_work: '#b0442e',
  overdue: '#8e2a1a',
  unverifiable: '#9a9389',
};

/** One dot on the Floods row: a flood day reported, hollow when the flood came from a river or the sea. */
interface FloodDot {
  date: string;
  outlets: number;
  mapped: boolean;
  rain: boolean;
  place?: string;
}

/**
 * Years on one axis for the selected place: flood days, promises (made → due) and imagery dates, plus building
 * growth beside the channel. With no place selected, every place's flood days are shown, so recurring years stand out.
 */
/** Width of an element in CSS pixels, so the SVG can draw at 1:1 instead of stretching. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(1000);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export function SiteTimeline() {
  const [foldedOpen, setFoldedOpen] = useState(false);
  const [boxRef, W] = useWidth<HTMLDivElement>();
  const loaded = useStore((s) => s.sites);
  const selectedId = useStore((s) => s.selectedSiteId);
  const end = useMemo(() => Date.UTC(new Date().getUTCFullYear() + 1, 0, 1), []);
  // Start where the record starts: the news search (2014), unless a mapped flood is older.
  const startYear = useMemo(() => {
    let y = NEWS_START;
    for (const s of loaded?.sites ?? []) for (const f of s.floods) y = Math.min(y, +f.date.slice(0, 4));
    return y;
  }, [loaded]);
  const START = Date.UTC(startYear, 0, 1);
  const x = (iso: string) => LEFT + ((Date.parse(iso) - START) / (end - START)) * (W - LEFT - 10);
  const years = useMemo(() => {
    const out: number[] = [];
    for (let y = startYear; y <= new Date(end).getUTCFullYear(); y++) out.push(y);
    return out;
  }, [startYear, end]);

  if (!loaded) return <div className="site-tl empty" ref={boxRef}>Loading sites…</div>;
  const site = loaded.sites.find((s) => s.site_id === selectedId);

  // The Floods row matches the Floods card: every strong flood day, plus mapped floods, one dot per date.
  const dots: FloodDot[] = site
    ? (() => {
        const byDate = new Map<string, FloodDot>();
        for (const f of site.catalog_floods ?? [])
          if (f.strength !== 'area')
            byDate.set(f.date, { date: f.date, outlets: f.n_outlets, mapped: !!f.tier_a_event_id, rain: f.flood_type === 'pluvial' });
        for (const fl of site.floods) {
          const ex = byDate.get(fl.date);
          if (ex) ex.mapped = true;
          else byDate.set(fl.date, { date: fl.date, outlets: fl.n_reports, mapped: true, rain: true });
        }
        return [...byDate.values()];
      })()
    : loaded.sites.flatMap((s) =>
        (s.catalog_floods ?? [])
          .filter((f) => f.strength !== 'area')
          .map((f) => ({ date: f.date, outlets: f.n_outlets, mapped: !!f.tier_a_event_id, rain: f.flood_type === 'pluvial', place: s.name })),
      );
  const promises = site ? site.promise_ids.map((id) => loaded.promises[id]).filter(Boolean) : [];
  const built = site?.change.buildings_0_10m && !site.change.buildings_0_10m.excluded ? site.change.buildings_0_10m.by_year : null;
  const builtYears = built ? Object.keys(built).sort() : [];
  const bMax = built ? Math.max(...Object.values(built), 0.0001) : 1;

  const H = 18 + ROWS.length * ROW;
  const rowY = (i: number) => 18 + i * ROW + ROW / 2;

  return (
    <div className="site-tl-wrap">
      <button
        type="button"
        className="site-tl__fold"
        aria-expanded={foldedOpen}
        onClick={() => setFoldedOpen((v) => !v)}
      >
        Timeline {foldedOpen ? '▾' : '▸'}
      </button>
      <div className={`site-tl-body${foldedOpen ? ' is-open' : ''}`}>
    <div className="site-tl" ref={boxRef}>
      <div className="site-tl__head">
        <b>{site ? site.name : 'All places'}</b>
        <span className="card__hint">
          {site
            ? `${plural(dots.length, 'flood day')} on record · hollow dots: river or sea floods`
            : `${plural(dots.length, 'flood day')} reported across ${loaded.sites.length} places since ${NEWS_START}. Pick a place to see its promises and changes.`}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="site-tl__svg">
        {years.map((y) => (
          <g key={y}>
            <line x1={x(`${y}-01-01`)} x2={x(`${y}-01-01`)} y1={12} y2={H} className="site-tl__grid" />
            <text x={x(`${y}-07-01`)} y={10} textAnchor="middle" className="site-tl__year">{y}</text>
          </g>
        ))}
        {startYear < NEWS_START && (
          <rect
            x={x(`${startYear}-01-01`)}
            y={12}
            width={x(`${NEWS_START}-01-01`) - x(`${startYear}-01-01`)}
            height={H - 12}
            className="site-tl__unsearched"
          >
            <title>News not searched before {NEWS_START}</title>
          </rect>
        )}

        {ROWS.map((r, i) => (
          <text key={r} x={8} y={rowY(i) + 4} className="site-tl__row">{r}</text>
        ))}

        {dots.map((d, i) => (
          <circle
            key={`${d.date}-${i}`}
            cx={x(d.date)}
            cy={rowY(0)}
            r={Math.min(9, 3 + Math.sqrt(d.outlets))}
            className={`site-tl__flood${d.rain ? '' : ' site-tl__flood--hollow'}`}
          >
            <title>
              {`${fmtOn(d.date)} · ${plural(d.outlets, 'news outlet')}${d.mapped ? ' · mapped flood' : ''}${d.place ? ` · ${d.place}` : ''}`}
            </title>
          </circle>
        ))}

        {promises.map((p, i) => {
          const made = x(p.date_made);
          const due = p.due.date ? x(p.due.date) : x(new Date(Date.parse(p.date_made) + 365 * 864e5).toISOString());
          const y = rowY(1) + ((i % 3) - 1) * 6;
          return (
            <g key={p.promise_id}>
              <line x1={made} x2={due} y1={y} y2={y} stroke={STATUS_FILL[p.status]} strokeWidth={2} strokeDasharray={p.due.date ? undefined : '3 2'} />
              <rect x={made - 4} y={y - 4} width={8} height={8} transform={`rotate(45 ${made} ${y})`} fill={STATUS_FILL[p.status]} />
              <title>{`${p.what} · ${PROMISE_LABEL[p.status]} · made ${fmtOn(p.date_made)}${p.due.date ? `, due ${fmtOn(p.due.date)}` : ', 12-month grace'}`}</title>
            </g>
          );
        })}

        {site?.change.wayback
          .filter((im) => (im.resolution_m ?? 0) <= 2 && x(im.acq_date) >= LEFT)
          .map((im) => (
            <line key={im.acq_date} x1={x(im.acq_date)} x2={x(im.acq_date)} y1={rowY(2) - 7} y2={rowY(2) + 7} className="site-tl__img">
              <title>{`Imagery ${fmtOn(im.acq_date)}`}</title>
            </line>
          ))}

        {built &&
          builtYears.map((yr) => {
            const h = (built[yr] / bMax) * (ROW - 8);
            return (
              <rect key={yr} x={x(`${yr}-03-01`)} y={rowY(3) + (ROW - 8) / 2 - h} width={(W - LEFT) / years.length * 0.6} height={h} className="site-tl__built">
                <title>{`${yr}: ${(built[yr] * 100).toFixed(1)}% of land within 10 m of the channel built on`}</title>
              </rect>
            );
          })}
      </svg>
    </div>
      </div>
    </div>
  );
}
