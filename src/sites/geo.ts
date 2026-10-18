import type { Geometry, Position } from 'geojson';
import type { SiteRecord, VerdictConfidence } from './types';

const coordsOf = (g: Geometry): Position[] => {
  switch (g.type) {
    case 'Point':
      return [g.coordinates];
    case 'LineString':
    case 'MultiPoint':
      return g.coordinates;
    case 'MultiLineString':
    case 'Polygon':
      return g.coordinates.flat();
    case 'MultiPolygon':
      return g.coordinates.flat(2);
    default:
      return [];
  }
};

/** Where to put a site's marker: the point itself, or the middle vertex of a line. */
export function sitePoint(s: SiteRecord): [number, number] {
  const c = coordsOf(s.geometry);
  const p = c[Math.floor(c.length / 2)] ?? [3.4, 6.5];
  return [p[0], p[1]];
}

/** [[west, south], [east, north]] with a small pad so short lines don't zoom in too far. */
export function siteBounds(s: SiteRecord, padDeg = 0.004): [[number, number], [number, number]] {
  const c = coordsOf(s.geometry);
  const xs = c.map((p) => p[0]);
  const ys = c.map((p) => p[1]);
  return [
    [Math.min(...xs) - padDeg, Math.min(...ys) - padDeg],
    [Math.max(...xs) + padDeg, Math.max(...ys) + padDeg],
  ];
}

type RGB = [number, number, number];
export const VERDICT_COLOR: Record<VerdictConfidence | 'unreviewed', RGB> = {
  strong: [164, 52, 30],
  moderate: [214, 120, 40],
  weak: [214, 178, 80],
  none: [150, 144, 134],
  unreviewed: [190, 184, 174],
};
export const verdictKey = (s: SiteRecord) => (s.verdict ? s.verdict.confidence : 'unreviewed');
