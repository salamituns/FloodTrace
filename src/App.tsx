import { useEffect } from 'react';
import { AreaPanel } from './components/AreaPanel';
import { Charts } from './components/Charts';
import { KeyEvents } from './components/KeyEvents';
import { MapView } from './components/MapView';
import { RightPanel } from './components/RightPanel';
import { SitePanel } from './components/SitePanel';
import { SiteTimeline } from './components/SiteTimeline';
import { Timeline } from './components/Timeline';
import { TopBar } from './components/TopBar';
import { loadCatalog, loadEvent } from './events/load';
import { areaHash, parseAreaHash } from './lib/area';
import { HOUR } from './lib/time';
import { loadSites } from './sites/load';
import { useStore } from './state/store';
import './styles/phone.css';

const DEFAULT_EVENT = 'lagos-2024-07-03';

/** The single clock: advances currentTime while playing. Everything else only reads it. */
function useClockDriver() {
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const { playing, speed, currentTime, t1, setTime, setPlaying } = useStore.getState();
      if (playing) {
        const next = currentTime + dt * speed * HOUR;
        setTime(next);
        if (next >= t1) setPlaying(false);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
}

/** Keeps mode, selected site, and the area pin in the URL hash so a view can be shared. */
function useHashSync() {
  useEffect(() => {
    const apply = () => {
      const area = parseAreaHash(location.hash);
      if (area) {
        const cur = useStore.getState().selectedArea;
        if (!cur || cur.lon !== area.lon || cur.lat !== area.lat || cur.label !== area.label) {
          // A shared area link with no ?event opens over the places map, not a flood replay.
          if (!new URLSearchParams(location.search).has('event')) useStore.getState().setMode('sites');
          useStore.getState().openArea(area);
        }
        return;
      }
      const h = new URLSearchParams(location.hash.slice(1));
      const site = h.get('site');
      if (site || h.has('sites')) {
        useStore.getState().setMode('sites');
        useStore.getState().selectSite(site);
      }
    };
    apply();
    window.addEventListener('hashchange', apply);
    const unsub = useStore.subscribe((s, prev) => {
      if (s.mode === prev.mode && s.selectedSiteId === prev.selectedSiteId && s.selectedArea === prev.selectedArea) return;
      const next = s.selectedArea
        ? areaHash(s.selectedArea)
        : s.mode === 'sites'
          ? s.selectedSiteId
            ? `#site=${s.selectedSiteId}`
            : '#sites'
          : '';
      if (location.hash !== next) history.replaceState(null, '', `${location.pathname}${location.search}${next}`);
    });
    return () => {
      window.removeEventListener('hashchange', apply);
      unsub();
    };
  }, []);
}

/**
 * Fetch the site registry at startup (Incident mode links reports to their sites too), and again after Retry clears
 * the error.
 */
function useSitesLoader() {
  const failed = useStore((s) => s.sitesError !== null);
  useEffect(() => {
    const { sites, setSites } = useStore.getState();
    if (sites || failed) return;
    loadSites()
      .then((s) => setSites(s))
      .catch((err: unknown) => setSites(null, String(err)));
  }, [failed]);
}

export default function App() {
  const event = useStore((s) => s.event);
  const loadError = useStore((s) => s.loadError);
  const mode = useStore((s) => s.mode);
  const selectedArea = useStore((s) => s.selectedArea);
  useClockDriver();
  useHashSync();
  useSitesLoader();

  // Front door (Task 33): with no ?event= and no hash, land on the places list instead of the flood map.
  // The store's own default stays "incident"; ?event=… and #site=… still take you straight there.
  useEffect(() => {
    if (!new URLSearchParams(location.search).has('event') && !location.hash) {
      useStore.getState().setMode('sites');
    }
  }, []);

  useEffect(() => {
    const id = new URLSearchParams(location.search).get('event') ?? DEFAULT_EVENT;
    loadEvent(id)
      .then((e) => useStore.getState().setEvent(e))
      .catch((err: unknown) => useStore.getState().setLoadError(String(err)));
    loadCatalog()
      .then((c) => useStore.getState().setCatalog(c))
      .catch(() => useStore.getState().setCatalog([]));
  }, []);

  if (!event) {
    return <div className="loading">{loadError ? `Could not load event: ${loadError}` : 'Loading event data…'}</div>;
  }
  // DOM order is the keyboard order (top bar → panel → map → timeline). Grid areas place
  // the map to the left on desktop and above the panel on a phone.
  return (
    <div className={`app${mode === 'sites' ? ' app--sites' : ''}`}>
      <TopBar />
      {selectedArea ? <AreaPanel /> : mode === 'sites' ? <SitePanel /> : <RightPanel />}
      <MapView />
      {mode === 'sites' ? (
        <div className="bottom bottom--sites">
          <SiteTimeline />
        </div>
      ) : (
        <div className="bottom">
          <Timeline />
          <Charts />
          <KeyEvents />
        </div>
      )}
    </div>
  );
}
