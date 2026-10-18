import { create } from 'zustand';
import type { CatalogEntry, LoadedEvent } from '../events/types';
import type { LoadedSites } from '../sites/types';
import { QUANT, setTimeZone } from '../lib/time';

export type LayerId = 'builtup' | 'buildings3d' | 'drainage' | 'sarFlood' | 'rainCells' | 'rainGrid' | 'evidence' | 'points';

export interface LayerState {
  visible: boolean;
  opacity: number;
}

export const LAYER_DEFS: { id: LayerId; label: string; swatch: string; hasOpacity: boolean }[] = [
  { id: 'evidence', label: 'Media evidence', swatch: 'radial-gradient(circle,#d4452f 30%,#f3d9d2 34%)', hasOpacity: true },
  { id: 'rainGrid', label: 'Rainfall rate (IMERG)', swatch: 'linear-gradient(135deg,#bfe0f5,#3d7fc4 55%,#7a3fb0)', hasOpacity: true },
  { id: 'sarFlood', label: 'Radar flood extent (S1)', swatch: 'linear-gradient(135deg,#f08a5d,#e2572b)', hasOpacity: true },
  { id: 'rainCells', label: 'Radar rain cells (S1)', swatch: 'linear-gradient(135deg,#9be3f2,#22c3e6)', hasOpacity: true },
  { id: 'drainage', label: 'Drainage & canals (OSM)', swatch: 'repeating-linear-gradient(160deg,#cfe0ec 0 2px,#2f7fb6 2px 4px)', hasOpacity: true },
  { id: 'builtup', label: 'Built over since 2000 (GHSL)', swatch: 'linear-gradient(135deg,#f6e7c8,#c9852f 55%,#7a3b12)', hasOpacity: true },
  { id: 'points', label: 'Analysis points', swatch: 'radial-gradient(circle,#2b2824 25%,#eee 28%)', hasOpacity: false },
  { id: 'buildings3d', label: 'Buildings (3D view)', swatch: 'repeating-conic-gradient(#ece6da 0 25%,#b9b1a2 0 50%) 0 0/8px 8px', hasOpacity: false },
];

/** Incident = one event on its own clock; Sites = places across all events and years. */
export type AppMode = 'incident' | 'sites';

export const SPEEDS = [1, 2, 4, 8]; // sim hours per real second

interface AppState {
  event: LoadedEvent | null;
  catalog: CatalogEntry[];
  loadError: string | null;
  t0: number;
  t1: number;
  currentTime: number;
  playing: boolean;
  speed: number;
  viewMode: '2d' | '3d';
  layers: Record<LayerId, LayerState>;
  selectedEventId: string | null;
  rainPoint: string;
  mode: AppMode;
  sites: LoadedSites | null;
  sitesError: string | null;
  selectedSiteId: string | null;
  /** Claim to highlight on the site page after following a cause chip from Incident mode. */
  focusClaimId: string | null;
  setEvent: (e: LoadedEvent) => void;
  setCatalog: (c: CatalogEntry[]) => void;
  setLoadError: (msg: string) => void;
  setTime: (t: number) => void;
  setPlaying: (p: boolean) => void;
  togglePlay: () => void;
  cycleSpeed: () => void;
  setViewMode: (m: '2d' | '3d') => void;
  setLayer: (id: LayerId, patch: Partial<LayerState>) => void;
  selectEvent: (id: string | null) => void;
  setRainPoint: (p: string) => void;
  setMode: (m: AppMode) => void;
  setSites: (s: LoadedSites | null, error?: string) => void;
  selectSite: (id: string | null) => void;
  openSite: (siteId: string, claimId?: string) => void;
}

export const useStore = create<AppState>()((set, get) => ({
  event: null,
  catalog: [],
  loadError: null,
  t0: 0,
  t1: 1,
  currentTime: 0,
  playing: false,
  speed: 1,
  viewMode: '2d',
  layers: {
    evidence: { visible: true, opacity: 1 },
    rainGrid: { visible: true, opacity: 0.4 },
    sarFlood: { visible: true, opacity: 0.85 },
    rainCells: { visible: true, opacity: 0.6 },
    drainage: { visible: true, opacity: 0.8 },
    points: { visible: true, opacity: 1 },
    builtup: { visible: false, opacity: 0.6 },
    buildings3d: { visible: true, opacity: 1 },
  },
  selectedEventId: null,
  rainPoint: 'lekki',
  mode: 'incident',
  sites: null,
  sitesError: null,
  selectedSiteId: null,
  focusClaimId: null,
  setEvent: (event) => {
    setTimeZone(event.timezone);
    // Open on the radar pass if there is one: the single moment with a direct observation.
    const start = event.sar?.observedAt ?? event.focus.start;
    set({ event, t0: event.focus.start, t1: event.focus.end, currentTime: start, playing: false, selectedEventId: null });
  },
  setCatalog: (catalog) => set({ catalog }),
  setLoadError: (loadError) => set({ loadError }),
  setTime: (t) => {
    const { t0, t1 } = get();
    set({ currentTime: Math.min(t1, Math.max(t0, t)) });
  },
  setPlaying: (playing) => set({ playing }),
  togglePlay: () =>
    set((s) => (s.playing ? { playing: false } : { playing: true, currentTime: s.currentTime >= s.t1 ? s.t0 : s.currentTime })),
  cycleSpeed: () => set((s) => ({ speed: SPEEDS[(SPEEDS.indexOf(s.speed) + 1) % SPEEDS.length] })),
  setViewMode: (viewMode) => set({ viewMode }),
  setLayer: (id, patch) => set((s) => ({ layers: { ...s.layers, [id]: { ...s.layers[id], ...patch } } })),
  selectEvent: (selectedEventId) => set({ selectedEventId }),
  setRainPoint: (rainPoint) => set({ rainPoint }),
  setMode: (mode) => set({ mode, playing: false }),
  setSites: (sites, sitesError) => set({ sites, sitesError: sitesError ?? null }),
  selectSite: (selectedSiteId) => set({ selectedSiteId, focusClaimId: null }),
  openSite: (selectedSiteId, claimId) => set({ mode: 'sites', playing: false, selectedSiteId, focusClaimId: claimId ?? null }),
}));

/** Time snapped to 15 min — for panels that shouldn't re-render every frame during playback. */
export const useQuantTime = () => useStore((s) => Math.floor(s.currentTime / QUANT) * QUANT);

/** Components below the loading gate can rely on the event being present. */
export const useEvent = () => useStore((s) => s.event!);
