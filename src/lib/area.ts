/** Street search and "Your area" helpers (Task 39).
 *
 * Matching and rain lookup run in the browser against static files. Typed
 * search text is never sent anywhere — the index is local.
 */

export const AREA_RADIUS_M = 1500
export const NEARBY_PLACES_M = 3000
export const HEAVY_RAIN_MM = 40

export type SearchKind =
  | 'street'
  | 'suburb'
  | 'neighbourhood'
  | 'quarter'
  | 'village'
  | 'town'
  | 'bus_station'
  | 'market'
  | 'school'
  | 'hospital'
  | 'clinic'
  | 'worship'
  | 'mall'
  | 'bridge'
  | 'estate'

export interface SearchItem {
  name: string
  alt?: string[]
  kind: SearchKind | string
  area: string | null
  lon: number
  lat: number
}

export interface SearchIndex {
  meta: { licence: string; by_kind: Record<string, number>; n: number }
  items: SearchItem[]
}

export interface AreaSelection {
  lon: number
  lat: number
  label: string
}

export type DepthPlacedBy = 'same_sentence' | 'single_area'

export interface FloodSpotDepth {
  phrase: string
  metres: number
  url: string | null
  publisher: string | null
  date?: string | null
  placed_by?: DepthPlacedBy
  sentence?: string
}

export interface FloodSpot {
  name: string
  lon: number
  lat: number
  confidence: 'street' | 'area' | 'neighbourhood' | string
  dates: string[]
  count: number
  latest: string
  reports: { url: string; publisher: string; date?: string }[]
  depths: FloodSpotDepth[]
}

export interface DepthUnplaced {
  phrase: string
  url: string
  reason: string
}

export interface FloodSpotsFile {
  meta: {
    dropped_city: number
    n_spots: number
    n_with_depth?: number
    depth_phrases: Record<string, number>
    depth_unplaced?: DepthUnplaced[]
  }
  spots: FloodSpot[]
}

export interface AreaRainCell {
  id: string
  lon: number
  lat: number
  heavy_days: number
  per_year: number
}

export interface AreaRainFile {
  meta: { threshold_mm: number; span_years: number }
  cells: AreaRainCell[]
}

export const KIND_LABEL: Record<string, string> = {
  street: 'street',
  suburb: 'suburb',
  neighbourhood: 'neighbourhood',
  quarter: 'quarter',
  village: 'village',
  town: 'town',
  bus_station: 'bus station',
  market: 'market',
  school: 'school',
  hospital: 'hospital',
  clinic: 'clinic',
  worship: 'place of worship',
  mall: 'mall',
  bridge: 'bridge',
  estate: 'estate',
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "3 Jul 2024" — WORDS.md prose dates. */
export function fmtOn(iso: string): string {
  return `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`
}

export function haversineM(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const r = 6371000
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dphi = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)))
}

export function fmtDistance(m: number): string {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`
}

/** A closed ring around a point, lon/lat pairs, for the 1.5 km "your area" circle. */
export function ringPolygon(lon: number, lat: number, radiusM: number, n = 64): [number, number][] {
  const out: [number, number][] = []
  for (let i = 0; i <= n; i++) {
    const brng = (2 * Math.PI * i) / n
    const lat1 = (lat * Math.PI) / 180
    const lon1 = (lon * Math.PI) / 180
    const ang = radiusM / 6371000
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(ang) + Math.cos(lat1) * Math.sin(ang) * Math.cos(brng))
    const lon2 =
      lon1 + Math.atan2(Math.sin(brng) * Math.sin(ang) * Math.cos(lat1), Math.cos(ang) - Math.sin(lat1) * Math.sin(lat2))
    out.push([((lon2 * 180) / Math.PI + 540) % 360 - 180, (lat2 * 180) / Math.PI])
  }
  return out
}

export function areaBounds(lon: number, lat: number, radiusM: number): [[number, number], [number, number]] {
  const pad = radiusM * 1.15
  const dLat = pad / 111320
  const dLon = pad / (111320 * Math.cos((lat * Math.PI) / 180))
  return [
    [lon - dLon, lat - dLat],
    [lon + dLon, lat + dLat],
  ]
}

export function fold(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

/** So "phase 1" and "phase I" are the same token. */
function foldToken(t: string): string {
  const roman: Record<string, string> = { i: '1', ii: '2', iii: '3', iv: '4', v: '5' }
  return roman[t] ?? t
}

function levenshtein(a: string, b: string): number {
  if (a === b) return 0
  if (!a.length) return b.length
  if (!b.length) return a.length
  const row = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]
    row[0] = i
    for (let j = 1; j <= b.length; j++) {
      const cur = row[j]
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + cost)
      prev = cur
    }
  }
  return row[b.length]
}

/** Words that name a kind of place, not the place itself. */
const KIND_WORDS: Record<string, string[]> = {
  bus_station: ['bus', 'stop', 'station', 'terminal', 'bustop', 'busstop'],
  street: ['street', 'road', 'avenue', 'close', 'drive', 'way', 'expressway'],
  school: ['school', 'college'],
  hospital: ['hospital'],
  clinic: ['clinic'],
  market: ['market'],
  mall: ['mall'],
  bridge: ['bridge', 'flyover'],
  estate: ['estate'],
  suburb: ['suburb'],
}

/**
 * Prefix matches first, then a contains, then a 1–2 character typo on a token.
 * Kind words in the query ("bus stop") prefer that kind instead of having to
 * appear in the OSM name. Lower is better. Infinity = no match.
 */
export function scoreItem(query: string, item: SearchItem): number {
  const q = fold(query)
  if (q.length < 2) return Infinity
  const qTokens = q.split(' ').filter(Boolean)
  const kindHint = Object.entries(KIND_WORDS).find(([, words]) => words.some((w) => qTokens.includes(w)))
  const leftover = kindHint ? qTokens.filter((t) => !KIND_WORDS[kindHint[0]].includes(t)) : qTokens
  const names = [item.name, ...(item.alt ?? [])]
  let best = Infinity
  for (const raw of names) {
    const n = fold(raw)
    if (!n) continue
    if (n === q) best = Math.min(best, 0)
    else if (n.startsWith(q)) best = Math.min(best, 1)
    else if (n.split(' ').some((t) => t.startsWith(q))) best = Math.min(best, 2)
    else if (n.includes(q)) best = Math.min(best, 3)
    else {
      const tokens = (leftover.length ? leftover : qTokens).map(foldToken)
      const nTokens = n.split(' ').map(foldToken)
      let sum = 0
      let ok = true
      for (const t of tokens) {
        let td = Infinity
        for (const nt of nTokens) {
          if (nt === t) td = Math.min(td, 0)
          else if (t.length >= 3 && nt.startsWith(t)) td = Math.min(td, 0)
          else if (t.length >= 4) {
            const d = levenshtein(t, nt)
            if (d <= 1) td = Math.min(td, d)
          }
        }
        if (td === Infinity) {
          ok = false
          break
        }
        sum += td
      }
      if (ok && tokens.length) best = Math.min(best, 4 + sum)
    }
  }
  if (best === Infinity && kindHint && leftover.length === 0 && item.kind === kindHint[0]) best = 6
  if (best === Infinity) return Infinity
  if (kindHint && item.kind === kindHint[0]) return best
  if (kindHint) return best + 8
  return best
}

export const NEWS_LINKS_SHOWN = 4
export const SEARCH_COLLAPSE_M = 600

export interface NewsLink {
  url: string
  publisher: string
  date?: string
}

/** One row per URL, newest date first. */
export function uniqueNewsLinks(reports: NewsLink[]): NewsLink[] {
  const byUrl = new Map<string, NewsLink>()
  for (const r of reports) {
    if (!r.url) continue
    const prev = byUrl.get(r.url)
    if (!prev || (r.date ?? '') > (prev.date ?? '')) byUrl.set(r.url, r)
  }
  return [...byUrl.values()].sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''))
}

export function newsLinkText(r: NewsLink): string {
  return r.date ? `${r.publisher}, ${fmtOn(r.date)}` : r.publisher
}

function searchDetail(item: SearchItem): number {
  return (item.alt?.length ?? 0) * 10 + (item.area ? 1 : 0) + item.name.length / 100
}

/** Same normalised name and kind within 600 m → keep the more detailed row.
 *  300 m left both ends of a named bridge (Ojuelegba Road, 563 m) as two hits.
 */
export function collapseNearbySearchHits(
  items: SearchItem[],
  metres = SEARCH_COLLAPSE_M,
): SearchItem[] {
  const keep: SearchItem[] = []
  for (const item of items) {
    const hit = keep.findIndex(
      (other) =>
        other.kind === item.kind &&
        fold(other.name) === fold(item.name) &&
        haversineM(other.lon, other.lat, item.lon, item.lat) <= metres,
    )
    if (hit < 0) {
      keep.push(item)
      continue
    }
    const cur = keep[hit]
    const winner = searchDetail(item) > searchDetail(cur) ? item : cur
    const alts = [...(winner.alt ?? [])]
    const seen = new Set([winner.name, ...alts])
    for (const a of item.alt ?? []) {
      if (!seen.has(a)) {
        seen.add(a)
        alts.push(a)
      }
    }
    for (const a of cur.alt ?? []) {
      if (!seen.has(a)) {
        seen.add(a)
        alts.push(a)
      }
    }
    keep[hit] = alts.length ? { ...winner, alt: alts } : winner
  }
  return keep
}

export function searchPlaces(query: string, items: SearchItem[], limit = 8): SearchItem[] {
  const q = fold(query)
  if (q.length < 2) return []
  const ranked = items
    .map((item) => ({ item, score: scoreItem(query, item) }))
    .filter((x) => x.score < Infinity)
    .sort((a, b) => a.score - b.score || a.item.name.localeCompare(b.item.name) || (a.item.area ?? '').localeCompare(b.item.area ?? ''))
    .map((x) => x.item)
  return collapseNearbySearchHits(ranked, SEARCH_COLLAPSE_M).slice(0, limit)
}

export function spotsWithin(spots: FloodSpot[], lon: number, lat: number, radiusM: number): { spot: FloodSpot; m: number }[] {
  return spots
    .map((spot) => ({ spot, m: haversineM(lon, lat, spot.lon, spot.lat) }))
    .filter((x) => x.m <= radiusM)
    .sort((a, b) => a.m - b.m)
}

export function nearestRainCell(cells: AreaRainCell[], lon: number, lat: number): AreaRainCell | null {
  if (!cells.length) return null
  let best = cells[0]
  let d = haversineM(lon, lat, best.lon, best.lat)
  for (const c of cells) {
    const n = haversineM(lon, lat, c.lon, c.lat)
    if (n < d) {
      best = c
      d = n
    }
  }
  return best
}

export function areaHash(sel: AreaSelection): string {
  return `#area=${sel.lon},${sel.lat},${encodeURIComponent(sel.label)}`
}

export function parseAreaHash(hash: string): AreaSelection | null {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  const params = new URLSearchParams(raw)
  const v = params.get('area')
  if (!v) return null
  const parts = v.split(',')
  if (parts.length < 3) return null
  const lon = Number(parts[0])
  const lat = Number(parts[1])
  const label = decodeURIComponent(parts.slice(2).join(','))
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || !label) return null
  return { lon, lat, label }
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export function loadSearchIndex(): Promise<SearchIndex> {
  return fetchJson<SearchIndex>('/events/search_index.json')
}

export function loadFloodSpots(): Promise<FloodSpotsFile> {
  return fetchJson<FloodSpotsFile>('/events/flood_spots.json')
}

export function loadAreaRain(): Promise<AreaRainFile> {
  return fetchJson<AreaRainFile>('/events/area_rain.json')
}
