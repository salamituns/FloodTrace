import { useEffect } from 'react';
import { Charts } from './components/Charts';
import { KeyEvents } from './components/KeyEvents';
import { MapView } from './components/MapView';
import { RightPanel } from './components/RightPanel';
import { SitePanel } from './components/SitePanel';
import { SiteTimeline } from './components/SiteTimeline';
import { Timeline } from './components/Timeline';
import { TopBar } from './components/TopBar';
import { loadCatalog, loadEvent } from './events/load';
import { HOUR } from './lib/time';
import { loadSites } from './sites/load';
import { useStore } from './state/store';

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

/** Keeps mode and selected site in the URL hash (#sites, #site=<id>) so a site page can be shared as a link. */
function useHashSync() {
  useEffect(() => {
    const apply = () => {
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
      if (s.mode === prev.mode && s.selectedSiteId === prev.selectedSiteId) return;
      const next = s.mode === 'sites' ? (s.selectedSiteId ? `#site=${s.selectedSiteId}` : '#sites') : '';
      if (location.hash !== next) history.replaceState(null, '', `${location.pathname}${location.search}${next}`);
    });
    return () => {
      window.removeEventListener('hashchange', apply);
      unsub();
    };
  }, []);
}

/** Fetch the site registry the first time Sites mode opens, and again after Retry clears the error. */
function useSitesLoader() {
  const mode = useStore((s) => s.mode);
  const failed = useStore((s) => s.sitesError !== null);
  useEffect(() => {
    const { sites, setSites } = useStore.getState();
    if (mode !== 'sites' || sites || failed) return;
    loadSites()
      .then((s) => setSites(s))
      .catch((err: unknown) => setSites(null, String(err)));
  }, [mode, failed]);
}

export default function App() {
  const event = useStore((s) => s.event);
  const loadError = useStore((s) => s.loadError);
  const mode = useStore((s) => s.mode);
  useClockDriver();
  useHashSync();
  useSitesLoader();

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
  return (
    <div className={`app${mode === 'sites' ? ' app--sites' : ''}`}>
      <TopBar />
      <main className="workspace">
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
      </main>
      {mode === 'sites' ? <SitePanel /> : <RightPanel />}
    </div>
  );
}
