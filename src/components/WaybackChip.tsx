import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { Geometry } from 'geojson';
import type { WaybackChip as WaybackChipRec } from '../sites/types';
import { layoutForChip, projectGeom, WAYBACK_CREDIT } from '../sites/wayback';

const MARK = '#ffd600';

function useVisible<T extends HTMLElement>(rootMargin = '80px') {
  const ref = useRef<T>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) setVisible(true);
      },
      { rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin]);
  return [ref, visible] as const;
}

function Outline({
  geometry,
  zoom,
  left,
  top,
  station,
}: {
  geometry: Geometry;
  zoom: number;
  left: number;
  top: number;
  station?: { lon: number; lat: number };
}) {
  const { kind, pts } = projectGeom(geometry, zoom, { left, top });
  if (pts.length === 0) return null;
  if (kind === 'Point') {
    const { x: cx, y: cy } = pts[0];
    const r = 24;
    return (
      <g>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#000" strokeWidth={5} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={MARK} strokeWidth={3} />
        <line x1={cx - 2 * r} y1={cy} x2={cx + 2 * r} y2={cy} stroke="#000" strokeWidth={3} />
        <line x1={cx - 2 * r} y1={cy} x2={cx + 2 * r} y2={cy} stroke={MARK} strokeWidth={1} />
        <line x1={cx} y1={cy - 2 * r} x2={cx} y2={cy + 2 * r} stroke="#000" strokeWidth={3} />
        <line x1={cx} y1={cy - 2 * r} x2={cx} y2={cy + 2 * r} stroke={MARK} strokeWidth={1} />
      </g>
    );
  }
  const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ');
  return (
    <g>
      <path d={d} fill="none" stroke="#000" strokeWidth={5} strokeLinejoin="round" />
      <path d={d} fill="none" stroke={MARK} strokeWidth={3} strokeLinejoin="round" />
      {station &&
        (() => {
          const { pts: sp } = projectGeom(
            { type: 'Point', coordinates: [station.lon, station.lat] },
            zoom,
            { left, top },
          );
          const p = sp[0];
          const r = 18;
          return (
            <>
              <circle cx={p.x} cy={p.y} r={r} fill="none" stroke="#000" strokeWidth={4} />
              <circle cx={p.x} cy={p.y} r={r} fill="none" stroke={MARK} strokeWidth={2} />
            </>
          );
        })()}
    </g>
  );
}

/** One north-up Wayback crop: a grid of live Esri tiles plus the site outline. */
export function WaybackChipView({
  chip,
  geometry,
  alt,
  className,
}: {
  chip: WaybackChipRec;
  geometry: Geometry;
  alt: string;
  className?: string;
}) {
  const layout = layoutForChip(chip);
  const [hostRef, visible] = useVisible<HTMLDivElement>();
  const [gen, setGen] = useState(0);
  const [loaded, setLoaded] = useState(0);
  const [failed, setFailed] = useState(false);
  const n = layout.tiles.length;
  useEffect(() => {
    setLoaded(0);
    setFailed(false);
  }, [chip.tile_url, chip.zoom, chip.bounds.west, chip.bounds.north, gen]);
  const ready = visible && loaded >= n && n > 0 && !failed;
  return (
    <div
      ref={hostRef}
      className={`wb-chip${className ? ` ${className}` : ''}`}
      style={{ aspectRatio: `${layout.width} / ${layout.height}` }}
      role="img"
      aria-label={alt}
    >
      {visible &&
        layout.tiles.map((t) => (
          <img
            key={`${gen}-${t.key}`}
            className="wb-chip__tile"
            alt=""
            draggable={false}
            src={t.url}
            style={{
              left: `${(t.x / layout.width) * 100}%`,
              top: `${(t.y / layout.height) * 100}%`,
              width: `${(256 / layout.width) * 100}%`,
              height: `${(256 / layout.height) * 100}%`,
              visibility: failed ? 'hidden' : 'visible',
            }}
            onLoad={() => setLoaded((c) => c + 1)}
            onError={() => setFailed(true)}
          />
        ))}
      <svg className="wb-chip__mark" viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true">
        <Outline
          geometry={geometry}
          zoom={chip.zoom}
          left={layout.left}
          top={layout.top}
          station={chip.lon != null && chip.lat != null ? { lon: chip.lon, lat: chip.lat } : undefined}
        />
      </svg>
      {!ready && !failed && <div className="wb-chip__ph">{visible ? 'Loading imagery…' : ''}</div>}
      {failed && (
        <div className="wb-chip__fail">
          <span>Imagery couldn't load</span>
          <button type="button" onClick={() => setGen((g) => g + 1)}>
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

export { WAYBACK_CREDIT };

/** Two dated chips; the range (and a touch drag on the frame) reveals after over before. */
export function BeforeAfterSlider({
  before,
  after,
  beforeAlt,
  afterAlt,
  geometry,
  split,
  onSplit,
}: {
  before: WaybackChipRec;
  after: WaybackChipRec;
  beforeAlt: string;
  afterAlt: string;
  geometry: Geometry;
  split: number;
  onSplit: (n: number) => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const setFromEvent = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = frameRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    onSplit(Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)));
  };
  return (
    <>
      <div
        className="ba__frame"
        ref={frameRef}
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          setFromEvent(e);
        }}
        onPointerMove={(e) => {
          if (dragging.current) setFromEvent(e);
        }}
        onPointerUp={() => {
          dragging.current = false;
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
      >
        <WaybackChipView chip={before} geometry={geometry} alt={beforeAlt} />
        <div className="ba__top" style={{ clipPath: `inset(0 0 0 ${split}%)` }}>
          <WaybackChipView chip={after} geometry={geometry} alt={afterAlt} />
        </div>
        <span className="ba__divider" style={{ left: `${split}%` }} />
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={split}
        onChange={(e) => onSplit(+e.target.value)}
        aria-label="Before/after split"
      />
    </>
  );
}
