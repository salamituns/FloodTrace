import { MapboxOverlay, type MapboxOverlayProps } from '@deck.gl/mapbox';
import { GeoJsonLayer, PolygonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import type { PickingInfo } from '@deck.gl/core';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AttributionControl, Map, NavigationControl, ScaleControl, useControl, type MapRef } from 'react-map-gl/maplibre';
import type { BuiltupProps, EvidenceItem } from '../events/types';
import { siteBounds, sitePoint } from '../sites/geo';
import { buildWatchList } from '../lib/watchList';
import { EMPTY_RAIN_SUMMARY, PRIORITY_RGB } from './SitePanel';
import type { SiteRecord } from '../sites/types';
import { causeLabel } from '../lib/causes';
import { siteLinksForEvent } from '../sites/links';
import { RAIN_STOPS, rainColor } from '../lib/rainColor';
import { fmtClock, fmtDateTime, HOUR } from '../lib/time';
import { LAYER_DEFS, useEvent, useQuantTime, useStore } from '../state/store';
import { FullscreenIcon } from './Icons';
import '../styles/flood.css';

const STYLE = 'https://tiles.openfreemap.org/styles/positron';
const BUILDINGS_LAYER = 'ft-buildings-3d';

type RGBA = [number, number, number, number];

const KIND_COLOR: Record<EvidenceItem['props']['kind'], [number, number, number]> = {
  news_report: [212, 69, 47],
  news_photo: [226, 87, 43],
  video: [176, 52, 108],
  official_statement: [31, 106, 154],
  social_post: [229, 138, 43],
};

const KIND_LABEL: Record<EvidenceItem['props']['kind'], string> = {
  news_report: 'News report',
  news_photo: 'News photo',
  video: 'Video',
  official_statement: 'Official statement',
  social_post: 'Social post',
};

function rgbCss(rgb: [number, number, number]) {
  return `rgb(${rgb.join(',')})`;
}

function MapKey() {
  const layers = useStore((s) => s.layers);
  const event = useEvent();
  const mode = useStore((s) => s.mode);
  const t = useQuantTime();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  const grid = event.rainGrid;
  const step = grid ? Math.floor((t - grid.times[0]) / (grid.stepH * HOUR)) : -1;
  const gridStep = grid && step >= 0 && step < grid.times.length ? step : null;
  const rainOn = mode === 'incident' && Boolean(grid && layers.rainGrid.visible);
  const entries: { key: string; color: string; hollow?: boolean; square?: boolean; label: string }[] = [];
  if (mode === 'sites') {
    // Places mode: the markers carry the list's priority tiers (Task 35).
    entries.push(
      { key: 'prio-high', color: '#a3361f', label: 'High priority place' },
      { key: 'prio-medium', color: '#b97b10', label: 'Medium priority place' },
      { key: 'prio-low', color: '#5d574e', label: 'Low priority place' },
      { key: 'prio-lowest', color: '#9a9385', hollow: true, label: 'Lowest priority place' },
    );
  }
  if (mode === 'incident' && layers.evidence.visible && event.evidence.length) {
    entries.push({ key: 'now', color: rgbCss(KIND_COLOR.news_report), label: 'Reported by now' });
    entries.push({ key: 'later', color: rgbCss(KIND_COLOR.news_report), hollow: true, label: 'Reported later' });
    (Object.keys(KIND_COLOR) as EvidenceItem['props']['kind'][]).forEach((kind) => {
      if (event.evidence.some((e) => e.props.kind === kind)) {
        entries.push({ key: kind, color: rgbCss(KIND_COLOR[kind]), label: KIND_LABEL[kind] });
      }
    });
    entries.push({ key: 'size', color: '#2b2824', label: 'Marker size: how precisely the place is known' });
  }
  if (mode === 'incident' && event.sar && layers.sarFlood.visible) {
    entries.push({ key: 'radar', color: 'rgb(226, 87, 43)', square: true, label: LAYER_DEFS.find((d) => d.id === 'sarFlood')!.label });
  }
  if (mode === 'incident' && layers.points.visible) {
    entries.push({ key: 'points', color: '#2b2824', label: LAYER_DEFS.find((d) => d.id === 'points')!.label });
  }

  return (
    <div className="map-key">
      <div className="map-key__box">
        <button type="button" className="map-key__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          Key {open ? '▾' : '▸'}
        </button>
        {open && entries.length > 0 && (
          <ul className="map-key__list">
            {entries.map((row) => (
              <li key={row.key}>
                <span
                  className={`map-key__swatch${row.hollow ? ' map-key__swatch--hollow' : ''}${row.square ? ' map-key__swatch--square' : ''}`}
                  style={{ color: row.color, borderColor: row.color }}
                />
                {row.label}
              </li>
            ))}
          </ul>
        )}
      </div>
      {rainOn && (
        <div className="rain-legend">
          <span className="rain-legend__title" title={LAYER_DEFS.find((d) => d.id === 'rainGrid')?.note}>
            {LAYER_DEFS.find((d) => d.id === 'rainGrid')?.label} (mm/h), from 2 mm/h ·{' '}
            {grid && gridStep !== null ? `${fmtClock(grid.times[gridStep])}–${fmtClock(grid.times[gridStep] + grid.stepH * HOUR)}` : 'outside rain window'}
          </span>
          <span className="rain-legend__ramp">
            {RAIN_STOPS.filter((s) => s.mmH >= 2).map((s) => (
              <span key={s.mmH} style={{ background: `rgb(${s.rgb.join(',')})` }}>
                {s.mmH}
              </span>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}

const WATERWAY_COLOR: Record<string, RGBA> = {
  canal: [31, 95, 139, 255],
  river: [31, 95, 139, 255],
  drain: [74, 127, 181, 255],
  stream: [111, 159, 196, 255],
  ditch: [140, 180, 210, 255],
};

function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay({ ...props, interleaved: true }));
  overlay.setProps(props);
  return null;
}

/** Share of a ~1 km cell newly built over 2000→2020: transparent where little changed, dark brown where most was built. */
const BUILT_STOPS: { d: number; rgb: [number, number, number] }[] = [
  { d: 0.05, rgb: [246, 231, 200] },
  { d: 0.15, rgb: [232, 184, 112] },
  { d: 0.3, rgb: [201, 133, 47] },
  { d: 0.5, rgb: [122, 59, 18] },
];
function builtColor(d: number): RGBA {
  if (d < BUILT_STOPS[0].d) return [0, 0, 0, 0];
  const stop = [...BUILT_STOPS].reverse().find((s) => d >= s.d) ?? BUILT_STOPS[0];
  return [...stop.rgb, 200];
}
const pct = (x: number) => `${Math.round(x * 100)}%`;

/** Emphasise a snapshot layer near the moment it was observed; fade it elsewhere in the timeline. */
const snapshotAlpha = (t: number, observedAt: number) => (Math.abs(t - observedAt) <= 6 * HOUR ? 1 : 0.35);

interface RainCell {
  i: number;
  j: number;
  polygon: [number, number][];
  value: number | null;
}

function tooltip({ object, layer }: PickingInfo) {
  if (!object || !layer) return null;
  if (layer.id === 'rain-grid') {
    const c = object as RainCell;
    return { html: `<div class="tip"><b>${c.value === null ? 'no data' : `${c.value.toFixed(1)} mm/h`}</b><small title="NASA GPM IMERG">rain cell ${c.polygon[0][1].toFixed(2)}–${c.polygon[2][1].toFixed(2)}°N</small></div>` };
  }
  if (layer.id === 'site-markers' || layer.id === 'site-lines') {
    const site = (layer.id === 'site-lines' ? (object as { properties: { site: SiteRecord } }).properties.site : object) as SiteRecord;
    const events = new Set(site.floods.map((f) => f.event_id)).size;
    const days = (site.catalog_floods ?? []).filter((f) => f.strength !== 'area').length;
    return {
      html: `<div class="tip"><b>${site.name}</b><span>${site.structure_name}</span><small>${events} mapped flood${events === 1 ? '' : 's'} · ${days} flood day${days === 1 ? '' : 's'} reported${site.verdict ? ` · evidence: ${site.verdict.confidence}` : ' · not yet reviewed'}</small></div>`,
    };
  }
  if (layer.id === 'evidence') {
    const e = object as EvidenceItem;
    const when = e.t ? fmtDateTime(e.t) : 'time unknown';
    // Read on hover rather than subscribed: 13 sites, so recomputing the links per tooltip is cheap.
    const { sites, event } = useStore.getState();
    const linked = sites && event ? siteLinksForEvent(sites.sites, event.id).get(e.props.id) ?? [] : [];
    return {
      html: `<div class="tip"><b>${e.props.location_name}</b><span>${e.props.claim}</span>${
        e.props.quote ? `<q>${e.props.quote}</q>` : ''
      }<small>${e.props.publisher} · ${when} (${e.props.time_confidence}) · location: ${e.props.location_confidence}${
        e.props.read_status === 'headline_only' ? ' · headline only' : ''
      }${e.props.quote_check?.startsWith('not verifiable') ? ' · quote unverified' : ''
      }</small>${
        e.props.causes?.length
          ? `<span class="tip__cause">Blamed on: ${e.props.causes.map(causeLabel).join(', ')}${
              e.props.cause_who ? ` (${e.props.cause_who})` : e.props.cause_attributed_by ? ` (${e.props.cause_attributed_by})` : ''
            }</span>`
          : ''
      }${linked.length ? `<span class="tip__site">Part of place: ${linked.map((l) => l.site.name).join(', ')}</span>` : ''}</div>`,
    };
  }
  const p = (object as { properties?: Record<string, unknown> }).properties;
  if (!p) return null;
  if (layer.id === 'builtup') {
    const b = p as unknown as BuiltupProps;
    return { html: `<div class="tip"><b>${pct(b.d2000_2020)} of this km² built over 2000→2020</b><small>Built-up ${pct(b.b2000)} in 2000 → ${pct(b.b2020)} in 2020 · GHSL GHS-BUILT-S</small></div>` };
  }
  if (layer.id === 'sar-flood' || layer.id === 'rain-cells') {
    return { html: `<div class="tip"><b>${String(p.class).replace(/_/g, ' ')}</b><small>${p.area_ha} ha · confidence ${p.confidence}</small></div>` };
  }
  if (layer.id === 'drainage') {
    return { html: `<div class="tip"><b>${p.name ?? 'Unnamed'}</b><small>${p.waterway ?? 'water body'} · OSM ${p.osm_id}</small></div>` };
  }
  return null;
}

export function MapView() {
  const event = useEvent();
  const t = useQuantTime();
  const layers = useStore((s) => s.layers);
  const mode = useStore((s) => s.mode);
  const loaded = useStore((s) => s.sites);
  const sites = loaded?.sites;
  const selectedSiteId = useStore((s) => s.selectedSiteId);
  const selectSite = useStore((s) => s.selectSite);
  const openPlaceFromMap = useCallback(
    (id: string) => {
      selectSite(id);
      if (window.matchMedia('(max-width: 720px)').matches) {
        window.setTimeout(() => document.getElementById('place-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
      }
    },
    [selectSite],
  );
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const containerRef = useRef<HTMLElement>(null);
  const mapRef = useRef<MapRef>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  // The basemap's place-name layers are hidden in Places mode; their visibility is remembered so it can be restored.
  // (A plain record: "Map" here would collide with react-map-gl's Map component.)
  const placeVis = useRef<Record<string, string>>({});

  /** Priority tier per place, from the same three tests as the list (buildWatchList). Only the list's tie-breaks
   *  read the rain digest, so an empty one keeps the tiers identical without a fetch. */
  const tierOf = useMemo(() => {
    const m: Record<string, number> = {};
    if (loaded) for (const r of buildWatchList(loaded.sites, loaded.promises, EMPTY_RAIN_SUMMARY, new Date())) m[r.site_id] = r.tier;
    return m;
  }, [loaded]);

  const initialViewState = useMemo(() => {
    const p = event.points.lekki ?? Object.values(event.points)[0];
    // A phone-width map needs one zoom level less to show the same stretch of the city.
    const narrow = typeof window !== 'undefined' && window.innerWidth <= 720;
    return { longitude: p[0] - 0.08, latitude: p[1] + 0.03, zoom: narrow ? 9.4 : 10.6, pitch: 0, bearing: 0 };
  }, [event]);

  // Which 30-min rain interval contains the current time (null outside the grid's coverage).
  const grid = event.rainGrid;
  const step = grid ? Math.floor((t - grid.times[0]) / (grid.stepH * HOUR)) : -1;
  const gridStep = grid && step >= 0 && step < grid.times.length ? step : null;
  const rainCells = useMemo<RainCell[]>(() => {
    if (!grid) return [];
    const h = grid.cellDeg / 2;
    const cells: RainCell[] = [];
    grid.lat.forEach((la, i) =>
      grid.lon.forEach((lo, j) =>
        cells.push({ i, j, value: null, polygon: [[lo - h, la - h], [lo + h, la - h], [lo + h, la + h], [lo - h, la + h]] }),
      ),
    );
    return cells;
  }, [grid]);

  const siteLayers = useMemo(() => {
    if (!sites) return [];
    const lines = {
      type: 'FeatureCollection' as const,
      features: sites
        .filter((x) => x.geometry.type !== 'Point')
        .map((x) => ({ type: 'Feature' as const, geometry: x.geometry, properties: { site: x } })),
    };
    const sel = (x: SiteRecord) => x.site_id === selectedSiteId;
    // Markers and lines share the list's priority colours, so one colour means one thing on the map and in the list.
    const prio = (x: SiteRecord) => PRIORITY_RGB[tierOf[x.site_id] ?? 0] ?? PRIORITY_RGB[0];
    const hover = (pick: (info: PickingInfo) => SiteRecord | null) => (info: PickingInfo) =>
      setHoveredId(info.object ? pick(info)?.site_id ?? null : null);
    // Labels are curated, not collided: only the selected or hovered place plus the High-priority ones, so no two
    // place labels fight for the same pixels at the city view (deck.gl's CollisionFilterExtension is not a project
    // dependency, and the curated rule also keeps the default view calm).
    const labelled = sites.filter((x) => sel(x) || x.site_id === hoveredId || tierOf[x.site_id] === 3);
    return [
      new GeoJsonLayer({
        id: 'site-lines',
        data: lines,
        getLineColor: (f) => [...prio(f.properties.site), 230] as RGBA,
        getLineWidth: (f) => (sel(f.properties.site) ? 6 : 3.5),
        lineWidthUnits: 'pixels',
        lineCapRounded: true,
        pickable: true,
        onClick: (info) => openPlaceFromMap((info.object as { properties: { site: SiteRecord } }).properties.site.site_id),
        onHover: hover((info) => (info.object as { properties: { site: SiteRecord } }).properties.site),
        updateTriggers: { getLineColor: [tierOf], getLineWidth: selectedSiteId },
      }),
      new ScatterplotLayer<SiteRecord>({
        id: 'site-markers',
        data: sites,
        getPosition: sitePoint,
        getRadius: (x) => (sel(x) ? 11 : 8),
        radiusUnits: 'pixels',
        getFillColor: (x) => [...prio(x), 235] as RGBA,
        getLineColor: (x) => (sel(x) ? [43, 40, 36, 255] : [255, 255, 255, 255]),
        stroked: true,
        lineWidthMinPixels: 2,
        pickable: true,
        onClick: (info) => openPlaceFromMap((info.object as SiteRecord).site_id),
        onHover: hover((info) => info.object as SiteRecord),
        updateTriggers: { getFillColor: [tierOf], getRadius: selectedSiteId, getLineColor: selectedSiteId },
      }),
      new TextLayer<SiteRecord>({
        id: 'site-labels',
        data: labelled,
        getPosition: sitePoint,
        getText: (x) => x.name,
        getSize: 11.5,
        getColor: [43, 40, 36, 255],
        getPixelOffset: [0, -16],
        fontFamily: 'Inter, sans-serif',
        fontWeight: 600,
        outlineWidth: 3,
        outlineColor: [255, 255, 255, 230],
        fontSettings: { sdf: true },
        characterSet: 'auto',
      }),
    ];
  }, [sites, selectedSiteId, hoveredId, tierOf, openPlaceFromMap]);

  // Fly to a place when it's selected, and keep it in view when "Replay this flood" switches to One flood mode
  // (wider there, so the event's reports around the place stay visible). mapReady waits for the map itself, so a
  // direct #site= link fits its place too, not just a click.
  useEffect(() => {
    if (!mapReady) return;
    const site = sites?.find((x) => x.site_id === selectedSiteId);
    if (!site) return;
    mapRef.current?.fitBounds(siteBounds(site), { padding: 80, maxZoom: mode === 'sites' ? 16 : 14, duration: 900 });
  }, [mapReady, mode, sites, selectedSiteId]);

  const eventLayers = useMemo(() => {
    const out = [];
    // Context layer, drawn first so rain and evidence sit on top of it.
    if (event.builtup && layers.builtup.visible) {
      out.push(
        new GeoJsonLayer<BuiltupProps>({
          id: 'builtup',
          data: event.builtup,
          opacity: layers.builtup.opacity,
          stroked: false,
          getFillColor: (f) => builtColor(f.properties.d2000_2020),
          pickable: true,
        }),
      );
    }
    if (grid && gridStep !== null && layers.rainGrid.visible) {
      const frame = grid.data[gridStep];
      out.push(
        new PolygonLayer<RainCell>({
          id: 'rain-grid',
          data: rainCells.map((c) => ({ ...c, value: frame[c.i][c.j] })),
          opacity: layers.rainGrid.opacity,
          getPolygon: (c) => c.polygon,
          getFillColor: (c) => (c.value === null || c.value < 2 ? [0, 0, 0, 0] : rainColor(c.value)),
          stroked: false,
          pickable: true,
        }),
      );
    }
    if (layers.drainage.visible) {
      out.push(
        new GeoJsonLayer({
          id: 'drainage',
          data: event.drainage,
          opacity: layers.drainage.opacity,
          stroked: true,
          filled: true,
          getFillColor: [120, 170, 205, 60],
          getLineColor: (f) => WATERWAY_COLOR[(f.properties?.waterway as string) ?? ''] ?? [90, 140, 180, 200],
          getLineWidth: (f) => (['canal', 'river'].includes(f.properties?.waterway) ? 3 : 1.5),
          lineWidthUnits: 'pixels',
          pickable: true,
        }),
      );
    }
    if (event.sar && layers.rainCells.visible) {
      const a = snapshotAlpha(t, event.sar.observedAt);
      out.push(
        new GeoJsonLayer({
          id: 'rain-cells',
          data: event.sar.rainCells,
          opacity: layers.rainCells.opacity * a,
          getFillColor: [34, 195, 230, 150],
          getLineColor: [16, 140, 175, 220],
          getLineWidth: 1,
          lineWidthUnits: 'pixels',
          pickable: true,
        }),
      );
    }
    if (event.sar && layers.sarFlood.visible) {
      const a = snapshotAlpha(t, event.sar.observedAt);
      out.push(
        new GeoJsonLayer({
          id: 'sar-flood',
          data: event.sar.flood,
          opacity: layers.sarFlood.opacity * a,
          getFillColor: (f) => (f.properties?.class === 'receded' ? [242, 164, 74, 200] : [226, 87, 43, 220]),
          getLineColor: [150, 50, 20, 255],
          getLineWidth: 1,
          lineWidthUnits: 'pixels',
          pickable: true,
        }),
      );
    }
    if (layers.points.visible) {
      const pts = Object.entries(event.points)
        .filter(([k]) => k !== 'offshore_tide')
        .map(([name, position]) => ({ name: name.replace(/_/g, ' '), position }));
      out.push(
        new ScatterplotLayer({
          id: 'points',
          data: pts,
          getPosition: (d) => d.position,
          getRadius: 5,
          radiusUnits: 'pixels',
          getFillColor: [43, 40, 36, 230],
          getLineColor: [255, 255, 255, 255],
          stroked: true,
          lineWidthMinPixels: 1.5,
        }),
        new TextLayer({
          id: 'points-label',
          data: pts,
          getPosition: (d) => d.position,
          getText: (d) => d.name,
          getSize: 12,
          getColor: [43, 40, 36, 255],
          getPixelOffset: [0, -14],
          fontFamily: 'Inter, sans-serif',
          fontWeight: 600,
          outlineWidth: 3,
          outlineColor: [255, 255, 255, 230],
          fontSettings: { sdf: true },
        characterSet: 'auto',
        }),
      );
    }
    if (layers.evidence.visible && event.evidence.length) {
      out.push(
        new ScatterplotLayer<EvidenceItem>({
          id: 'evidence',
          data: event.evidence,
          opacity: layers.evidence.opacity,
          getPosition: (d) => d.position,
          getRadius: (d) => (d.props.location_confidence === 'point' ? 7 : d.props.location_confidence === 'street' ? 9 : 12),
          radiusUnits: 'pixels',
          // Reports not yet made at the current time are drawn hollow.
          getFillColor: (d) => (d.t !== null && d.t <= t ? [...KIND_COLOR[d.props.kind], 210] : [255, 255, 255, 140]) as RGBA,
          getLineColor: (d) => [...KIND_COLOR[d.props.kind], 255] as RGBA,
          stroked: true,
          lineWidthMinPixels: 2,
          pickable: true,
          updateTriggers: { getFillColor: t },
        }),
      );
    }
    return out;
  }, [event, layers, t, grid, gridStep, rainCells]);

  // Sites mode keeps only context (built-up change, drainage) under the site layers; event layers are hidden.
  const deckLayers = useMemo(
    () =>
      mode === 'sites'
        ? [...eventLayers.filter((l) => l.id === 'builtup' || l.id === 'drainage'), ...siteLayers]
        : eventLayers,
    [mode, eventLayers, siteLayers],
  );

  const setBuildingsVisible = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map?.getLayer(BUILDINGS_LAYER)) return;
    map.setLayoutProperty(BUILDINGS_LAYER, 'visibility', viewMode === '3d' && layers.buildings3d.visible ? 'visible' : 'none');
  }, [viewMode, layers.buildings3d.visible]);

  // Add an extrusion layer from the basemap's OpenMapTiles building data (positron has none of its own).
  const onLoad = useCallback(() => {
    setMapReady(true);
    const map = mapRef.current?.getMap();
    // MapLibre re-expands the compact attribution whenever a source adds credits. Keep it folded behind its (i)
    // button until the reader opens it themselves.
    if (map) {
      let opened = false;
      const fold = () => {
        if (!opened) map.getContainer().querySelector('.maplibregl-compact-show')?.classList.remove('maplibregl-compact-show');
      };
      map.getContainer().querySelector('.maplibregl-ctrl-attrib-button')?.addEventListener('click', () => (opened = true), { once: true });
      map.on('data', fold);
      fold();
    }
    if (!map || map.getLayer(BUILDINGS_LAYER)) return;
    const source = Object.keys(map.getStyle().sources).find((k) => map.getSource(k)?.type === 'vector') ?? 'openmaptiles';
    map.addLayer({
      id: BUILDINGS_LAYER,
      type: 'fill-extrusion',
      source,
      'source-layer': 'building',
      minzoom: 13,
      layout: { visibility: 'none' },
      paint: {
        'fill-extrusion-color': '#ddd6ca',
        'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 6],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
        'fill-extrusion-opacity': 0.85,
      },
    });
    setBuildingsVisible();
  }, [setBuildingsVisible]);

  /** The positron basemap names neighbourhoods from its "place" layers; on the Places screen our own labels
   *  win, so the basemap's are hidden (the style allows layout changes) and restored when the flood view returns.
   *  Where the style has no such layers, the white halo on our labels is the fallback. */
  const setBasemapPlaces = useCallback((hidden: boolean) => {
    const map = mapRef.current?.getMap();
    if (!map || !map.isStyleLoaded()) return;
    for (const l of map.getStyle().layers) {
      const sourceLayer = 'source-layer' in l ? (l as { 'source-layer'?: string })['source-layer'] : undefined;
      const isPlace = sourceLayer === 'place' || /^place/i.test(l.id) || /^label_/i.test(l.id);
      if (l.type !== 'symbol' || !isPlace) continue;
      if (hidden) {
        if (!(l.id in placeVis.current)) placeVis.current[l.id] = String(map.getLayoutProperty(l.id, 'visibility') ?? 'visible');
        map.setLayoutProperty(l.id, 'visibility', 'none');
      } else if (l.id in placeVis.current) {
        map.setLayoutProperty(l.id, 'visibility', placeVis.current[l.id]);
        delete placeVis.current[l.id];
      }
    }
  }, []);
  useEffect(() => {
    if (mapReady) setBasemapPlaces(mode === 'sites');
  }, [mode, mapReady, setBasemapPlaces]);

  // Street-zoom leftover: punch a ~60 px hole in remaining point labels around the selected place.
  // Line labels (road names) cannot take MapLibre's `within` filter; those we leave and note in the report.
  const labelFilters = useRef<Record<string, maplibregl.FilterSpecification | null>>({});
  useEffect(() => {
    const map = mapRef.current?.getMap();
    const site = sites?.find((x) => x.site_id === selectedSiteId);
    const restore = () => {
      if (!map?.isStyleLoaded()) return;
      for (const [id, filter] of Object.entries(labelFilters.current)) {
        if (map.getLayer(id)) map.setFilter(id, filter ?? null);
        delete labelFilters.current[id];
      }
    };
    if (!mapReady || !map || mode !== 'sites' || !site) {
      restore();
      return;
    }
    const apply = () => {
      if (!map.isStyleLoaded() || map.getZoom() < 14) {
        restore();
        return;
      }
      const pt = map.project(sitePoint(site));
      const a = map.unproject([pt.x - 60, pt.y - 60]);
      const b = map.unproject([pt.x + 60, pt.y + 60]);
      const west = Math.min(a.lng, b.lng);
      const east = Math.max(a.lng, b.lng);
      const south = Math.min(a.lat, b.lat);
      const north = Math.max(a.lat, b.lat);
      const poly = {
        type: 'Polygon' as const,
        coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
      };
      for (const l of map.getStyle().layers) {
        if (l.type !== 'symbol') continue;
        const sl = 'source-layer' in l ? (l as { 'source-layer'?: string })['source-layer'] : undefined;
        if (sl !== 'place' && sl !== 'water_name' && sl !== 'aerodrome_label' && sl !== 'transportation_name') continue;
        try {
          if (!(l.id in labelFilters.current)) labelFilters.current[l.id] = map.getFilter(l.id) ?? null;
          const prev = labelFilters.current[l.id];
          const next = (prev ? ['all', prev, ['!', ['within', poly]]] : ['!', ['within', poly]]) as never;
          map.setFilter(l.id, next);
        } catch {
          // Line or other geometries reject `within`; leave that layer as-is.
        }
      }
    };
    apply();
    map.on('moveend', apply);
    return () => {
      map.off('moveend', apply);
      restore();
    };
  }, [mapReady, mode, sites, selectedSiteId]);

  const switchView = (m: '2d' | '3d') => {
    setViewMode(m);
    mapRef.current?.easeTo({ pitch: m === '3d' ? 58 : 0, bearing: m === '3d' ? -20 : 0, duration: 800 });
  };
  useEffect(setBuildingsVisible, [setBuildingsVisible]);

  const fullscreen = () => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen();
  };

  return (
    <section
      className="map"
      ref={containerRef}
      aria-label={mode === 'sites' ? 'Map of Lagos places that flood' : 'Map of this flood in Lagos'}
    >
      <Map
        ref={mapRef}
        mapLib={maplibregl}
        initialViewState={initialViewState}
        mapStyle={STYLE}
        onLoad={onLoad}
        maxPitch={70}
        attributionControl={false}
        style={{ width: '100%', height: '100%' }}
      >
        <DeckOverlay layers={deckLayers} getTooltip={tooltip} />
        <NavigationControl position="top-left" visualizePitch />
        <ScaleControl position="bottom-left" />
        <AttributionControl compact={true} position="bottom-right" customAttribution={`${event.sar ? `Contains modified Copernicus Sentinel data ${new Date(event.sar.observedAt).getUTCFullYear()} · ` : ''}${event.rainGrid ? 'NASA GPM IMERG · ' : ''}${event.builtup && layers.builtup.visible ? 'GHSL © EC JRC · ' : ''}OSM contributors`} />
      </Map>
      {mode === 'incident' && event.sar && (
        <div className="snapshot-badge">
          Radar snapshot · {fmtDateTime(event.sar.observedAt)}
          {Math.abs(t - event.sar.observedAt) > 6 * HOUR && <span> (faded: &gt;6 h from now)</span>}
        </div>
      )}
      <MapKey />
      {event.builtup && layers.builtup.visible && (
        <div className="rain-legend rain-legend--built">
          <span className="rain-legend__title">Share of km² built over 2000→2020</span>
          <span className="rain-legend__ramp">
            {BUILT_STOPS.map((s) => (
              <span key={s.d} style={{ background: `rgb(${s.rgb.join(',')})` }}
                className={s.d >= 0.3 ? 'is-dark' : ''}>
                {pct(s.d)}
              </span>
            ))}
          </span>
        </div>
      )}
      <div className="map-controls">
        <div className="segmented">
          {(['2d', '3d'] as const).map((m) => (
            <button key={m} className={viewMode === m ? 'is-active' : ''} onClick={() => switchView(m)}>
              {m.toUpperCase()}
            </button>
          ))}
        </div>
        <button className="icon-btn" onClick={fullscreen} aria-label="Fullscreen">
          <FullscreenIcon />
        </button>
      </div>
    </section>
  );
}
