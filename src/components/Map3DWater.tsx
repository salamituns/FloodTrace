/** 3D water (Task 40). Evidence water only: what was reported (depth quotes,
 *  drawn as water bodies) or seen (radar satellite). The terrain-only "rough
 *  model" layer was dropped on 21 Oct 2026: it matched reported floods no
 *  better than chance (events/rough_model/meta.json).
 */

import { GeoJsonLayer, PathLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers';
import type { Layer } from '@deck.gl/core';
import { KIND_LABEL, fmtDistance, fmtOn, ringPolygon, type FloodSpot } from '../lib/area';
import {
  classifyRoads,
  discRadiusM,
  type FacilitiesFile,
  type RoadLine,
  type RoadSegment,
  type WaterTest,
} from '../lib/impacts';

/** Water surfaces are drawn this many times taller than reality so depths stay
 *  visible beside real-scale buildings; every depth number shown is the real one. */
export const WATER_VEX = 20;
/** The same blue wherever water means water (WORDS.md). */
export const EVIDENCE_WATER_RGB: [number, number, number] = [61, 127, 196];
export const RADAR_WATER_LABEL = 'Seen by radar satellite, 3 Jul 2024';

export interface WaterBody {
  spot: FloodSpot;
  polygon: [number, number][];
}
export interface WaterArc {
  spot: FloodSpot;
  arc: [number, number][];
}
export interface WaterDisc {
  spot: FloodSpot;
  polygon: [number, number][];
  arcs: WaterArc[];
}

/** Only depths with a `placed_by` are drawn as water (Task 39b). */
export function placedDepths(spot: FloodSpot) {
  return spot.depths.filter((d) => d.placed_by);
}

function dashedArcs(ring: [number, number][], spot: FloodSpot): WaterArc[] {
  const arcs: WaterArc[] = [];
  ring.forEach((a, i) => {
    if (i + 1 >= ring.length) return;
    if (Math.floor(i / 2) % 2 !== 0) return; // alternate two-edge runs: a dashed circle
    arcs.push({ spot, arc: [a, ring[i + 1]] });
  });
  return arcs;
}

export function splitEvidenceWater(spots: FloodSpot[]): { bodies: WaterBody[]; discs: WaterDisc[] } {
  const bodies: WaterBody[] = [];
  const discs: WaterDisc[] = [];
  for (const s of spots) {
    const ring = ringPolygon(s.lon, s.lat, discRadiusM(s), 48);
    if (placedDepths(s).length > 0) bodies.push({ spot: s, polygon: ring });
    else discs.push({ spot: s, polygon: ring, arcs: dashedArcs(ring, s) });
  }
  return { bodies, discs };
}

export function evidenceWaterLayers(opts: {
  spots: FloodSpot[];
  radarFlood: GeoJSON.FeatureCollection | null;
  opacity: number;
}): Layer[] {
  const { bodies, discs } = splitEvidenceWater(opts.spots);
  const a = Math.round(126 * opts.opacity);
  const out: Layer[] = [];
  if (bodies.length) {
    out.push(
      new PolygonLayer<WaterBody>({
        id: 'water-bodies',
        data: bodies,
        getPolygon: (d) => d.polygon,
        extruded: true,
        // the surface is raised by the deepest reported depth × the map's water exaggeration
        getElevation: (d) => Math.max(0, ...placedDepths(d.spot).map((x) => x.metres)) * WATER_VEX,
        getFillColor: [...EVIDENCE_WATER_RGB, a],
        getLineColor: [31, 106, 154, 230],
        lineWidthMinPixels: 1,
        stroked: true,
        pickable: true,
      }),
    );
  }
  if (discs.length) {
    out.push(
      new PolygonLayer<WaterDisc>({
        id: 'water-discs',
        data: discs,
        getPolygon: (d) => d.polygon,
        extruded: false,
        getFillColor: [...EVIDENCE_WATER_RGB, Math.round(56 * opts.opacity)],
        stroked: false,
        pickable: true,
      }),
      new PathLayer<WaterArc>({
        id: 'water-discs-dash',
        data: discs.flatMap((d) => d.arcs),
        getPath: (d) => d.arc,
        getColor: [...EVIDENCE_WATER_RGB, Math.round(225 * opts.opacity)],
        getWidth: 2,
        widthUnits: 'pixels',
        pickable: true,
      }),
    );
  }
  const radar = (opts.radarFlood?.features ?? []).filter(
    (f) => (f.properties as { class?: string } | null)?.class === 'open_flood',
  );
  if (radar.length) {
    out.push(
      new GeoJsonLayer({
        id: 'radar-water',
        data: { type: 'FeatureCollection' as const, features: radar },
        filled: true,
        stroked: true,
        extruded: false,
        getFillColor: [...EVIDENCE_WATER_RGB, Math.round(88 * opts.opacity)],
        getLineColor: [...EVIDENCE_WATER_RGB, Math.round(200 * opts.opacity)],
        getLineWidth: 1,
        lineWidthUnits: 'pixels',
        pickable: true,
      }),
    );
  }
  return out;
}

// ── tooltips ─────────────────────────────────────────────────────────────

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** report url -> date, set by MapView once loaded so the sync tooltip can cite it. */
let reportDates: Map<string, string> | null = null;
export function setReportDatesForTooltips(dates: Map<string, string> | null) {
  reportDates = dates;
}

export function waterSpotTooltip(spot: FloodSpot): { html: string } {
  const quotes = placedDepths(spot)
    .map((d) => {
      const date = d.url ? reportDates?.get(d.url) : null;
      const source = `${d.publisher ?? 'news report'}${date ? `, ${fmtOn(date)}` : ''}`;
      return `<q title="${esc(d.sentence ?? '')}">${esc(d.phrase)}</q> (${esc(source)})`;
    })
    .join(' ');
  return {
    html:
      `<div class="tip"><b>${esc(spot.name)}</b>` +
      `<small>${spot.count} flood day${spot.count === 1 ? '' : 's'} reported · last ${fmtOn(spot.latest)}` +
      (spot.dates.length > 1 ? `<br>${spot.dates.map(fmtOn).join(', ')}` : '') +
      `</small>${quotes ? `<span class="tip__depth">${quotes}</span>` : '<small>Flooded, depth not reported.</small>'}</div>`,
  };
}

export function radarWaterTooltip(): { html: string } {
  return {
    html: `<div class="tip"><b>${RADAR_WATER_LABEL}</b><small>Sentinel-1 radar pass · open water only, misses water under buildings</small></div>`,
  };
}

export function roadSegmentTooltip(seg: RoadSegment): { html: string } {
  return {
    html: `<div class="tip"><b>${esc(seg.name)}</b><small>${seg.wet ? `about ${fmtDistance(seg.lengthM)} of this road sits in the water` : 'not in the water here'}</small></div>`,
  };
}

export function facilityTooltip(name: string, kind: string, wet: boolean): { html: string } {
  const label = KIND_LABEL[kind] ?? kind;
  return { html: `<div class="tip"><b>${esc(name || label)}</b><small>${label}${wet ? ' · inside the water' : ''}</small></div>` };
}

// ── what's hit: roads and facilities through the water (section D) ────────

export interface FacilityPoint {
  name: string;
  kind: string;
  position: [number, number];
  wet: boolean;
}

export function waterImpactLayers(opts: {
  center: { lon: number; lat: number };
  radiusM: number;
  test: WaterTest;
  roads: RoadLine[] | null;
  facilities: FacilitiesFile | null;
}): Layer[] {
  const out: Layer[] = [];
  const segs = opts.roads ? classifyRoads(opts.roads, opts.test, opts.center.lon, opts.center.lat, opts.radiusM) : [];
  if (segs.length) {
    out.push(
      new PathLayer<RoadSegment>({
        id: 'water-roads',
        data: segs,
        getPath: (d) => d.positions,
        getColor: (d) => (d.wet ? [47, 119, 184, 235] : [110, 108, 100, 110]),
        getWidth: (d) => (d.wet ? 4 : 1.5),
        widthUnits: 'pixels',
        pickable: true,
      }),
    );
  }
  const points: FacilityPoint[] = [];
  for (const f of opts.facilities?.features ?? []) {
    const [lon, lat] = f.geometry.coordinates;
    const dy = (lat - opts.center.lat) * 111320;
    const dx = (lon - opts.center.lon) * 111320 * Math.cos((opts.center.lat * Math.PI) / 180);
    if (dx * dx + dy * dy > opts.radiusM ** 2) continue;
    points.push({ name: f.properties.name, kind: f.properties.kind, position: [lon, lat], wet: opts.test.isWet(lon, lat) });
  }
  if (points.length) {
    out.push(
      new ScatterplotLayer<FacilityPoint>({
        id: 'water-facilities',
        data: points,
        getPosition: (d) => d.position,
        getRadius: 5,
        radiusUnits: 'pixels',
        getFillColor: (d) => (d.wet ? [...EVIDENCE_WATER_RGB, 235] : [140, 138, 130, 165]),
        getLineColor: [255, 255, 255, 210],
        stroked: true,
        lineWidthMinPixels: 1,
        pickable: true,
      }),
    );
  }
  return out;
}
