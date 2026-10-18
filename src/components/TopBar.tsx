import { fmtDay } from '../lib/time';
import { useEvent, useStore } from '../state/store';
import { EventSwitcher } from './EventSwitcher';
import { CalendarIcon, ChartIcon, Chevron, DroneIcon, GearIcon, LogoMark, MapIcon, PinIcon, ShareIcon, TruckIcon, ViewIcon } from './Icons';

export function TopBar() {
  const event = useEvent();
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  return (
    <header className="topbar">
      <div className="brand">
        <LogoMark />
        <span className="brand__name">FloodTrace</span>
        <span className="brand__sub">Flood Forensic Analysis</span>
      </div>
      <span className="topbar__sep" />
      {mode === 'incident' ? (
        <>
          <EventSwitcher />
          <span className="topbar__muted">Lagos, Nigeria</span>
          <span className="topbar__date">
            <CalendarIcon /> {fmtDay(event.focus.start)} – {fmtDay(event.focus.end)}, {new Date(event.focus.start).getUTCFullYear()}
          </span>
        </>
      ) : (
        <span className="topbar__muted">Lagos, Nigeria · places that keep flooding, across all events</span>
      )}

      <nav className="modes" aria-label="Mode">
        <button className={`mode${mode === 'incident' ? ' mode--active' : ''}`} aria-pressed={mode === 'incident'} onClick={() => setMode('incident')}>
          <MapIcon /> Incident
        </button>
        <button className={`mode${mode === 'sites' ? ' mode--active' : ''}`} aria-pressed={mode === 'sites'} onClick={() => setMode('sites')}>
          <PinIcon /> Sites
        </button>
        <button className="mode" disabled title="Later phase">
          <DroneIcon /> Imagery
        </button>
        <button className="mode" disabled title="Later phase">
          <TruckIcon /> Response
        </button>
      </nav>

      <div className="topbar__menus">
        <button className="menu"><ViewIcon /> View <Chevron /></button>
        <button className="menu"><ChartIcon /> Analysis <Chevron /></button>
        <button className="menu"><ShareIcon /> Share <Chevron /></button>
        <button className="menu menu--icon" aria-label="Settings"><GearIcon /></button>
      </div>
    </header>
  );
}
