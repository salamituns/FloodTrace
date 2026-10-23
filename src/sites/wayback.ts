import type { Geometry } from 'geojson';
import type { WaybackChip } from './types';

/** Shown under every live Wayback chip and on the map while those tiles are up. */
export const WAYBACK_CREDIT =
  'Imagery: Esri World Imagery Wayback (Esri, Maxar, Earthstar Geographics, and the GIS User Community)';

export interface WaybackTile {
  url: string;
  x: number;
  y: number;
  key: string;
}

export interface WaybackLayout {
  tiles: WaybackTile[];
  width: number;
  height: number;
  left: number;
  top: number;
}

export function lonlatToPx(lon: number, lat: number, z: number): [number, number] {
  const n = 256 * (1 << z);
  const x = ((lon + 180) / 360) * n;
  const clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
  const s = Math.sin((clamped * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n;
  return [x, y];
}

export function fillTileUrl(template: string, z: number, col: number, row: number): string {
  return template
    .split('{level}').join(String(z))
    .split('{col}').join(String(col))
    .split('{row}').join(String(row));
}

/** Same north-up mercator crop as `build_chip` in pipeline/site_imagery.py. */
export function layoutForChip(chip: Pick<WaybackChip, 'bounds' | 'zoom' | 'tile_url'>): WaybackLayout {
  const { bounds, zoom, tile_url: tileUrl } = chip;
  const corners: [number, number][] = [
    [bounds.west, bounds.south],
    [bounds.east, bounds.south],
    [bounds.east, bounds.north],
    [bounds.west, bounds.north],
  ];
  const xs = corners.map(([lon, lat]) => lonlatToPx(lon, lat, zoom)[0]);
  const ys = corners.map(([lon, lat]) => lonlatToPx(lon, lat, zoom)[1]);
  const left = Math.round(Math.min(...xs));
  const top = Math.round(Math.min(...ys));
  const right = Math.round(Math.max(...xs));
  const bottom = Math.round(Math.max(...ys));
  const tiles: WaybackTile[] = [];
  for (let ty = top >> 8; ty <= bottom >> 8; ty++) {
    for (let tx = left >> 8; tx <= right >> 8; tx++) {
      tiles.push({
        url: fillTileUrl(tileUrl, zoom, tx, ty),
        x: tx * 256 - left,
        y: ty * 256 - top,
        key: `${tx}/${ty}`,
      });
    }
  }
  return { tiles, width: Math.max(1, right - left), height: Math.max(1, bottom - top), left, top };
}

export function projectGeom(
  geometry: Geometry,
  zoom: number,
  origin: { left: number; top: number },
): { kind: 'Point' | 'Line'; pts: { x: number; y: number }[] } {
  const raw: [number, number][] =
    geometry.type === 'Point'
      ? [geometry.coordinates as [number, number]]
      : geometry.type === 'LineString'
        ? (geometry.coordinates as [number, number][])
        : [];
  const pts = raw.map(([lon, lat]) => {
    const [x, y] = lonlatToPx(lon, lat, zoom);
    return { x: x - origin.left, y: y - origin.top };
  });
  return { kind: geometry.type === 'Point' ? 'Point' : 'Line', pts };
}

