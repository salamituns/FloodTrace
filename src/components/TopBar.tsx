import { useEffect, useState } from 'react';
import { fmtDay } from '../lib/time';
import { useEvent, useStore } from '../state/store';
import { EventSwitcher } from './EventSwitcher';
import { HowToRead } from './HowToRead';
import { CalendarIcon, HelpIcon, LinkIcon, LogoMark, MapIcon, PinIcon } from './Icons';
import '../styles/places.css';

/** Remembers a dismissed guide; if storage is unavailable, dismissal lasts for this session only. */
const HOWTO_KEY = 'floodtrace:how-to-read-dismissed';

export function TopBar() {
  const event = useEvent();
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  // First visit: no dismissal on record. Storage failures fall back to showing it.
  const [howOpen, setHowOpen] = useState(() => {
    try {
      return localStorage.getItem(HOWTO_KEY) === null;
    } catch {
      return true;
    }
  });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(t);
  }, [copied]);

  const closeHowTo = () => {
    setHowOpen(false);
    try {
      localStorage.setItem(HOWTO_KEY, '1');
    } catch {
      // No storage: dismissed for this session only.
    }
  };

  const copyLink = async () => {
    const url = location.href;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.readOnly = true;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } catch {
        // Clipboard unavailable; the control still answers so it never looks dead.
      }
      ta.remove();
    }
    setCopied(true);
  };

  return (
    <header className="topbar">
      <div className="brand">
        <LogoMark />
        <h1 className="brand__name">FloodTrace</h1>
        <span className="brand__sub">Lagos: where it floods, why, and what was fixed</span>
      </div>
      {mode === 'incident' && (
        <div className="topbar__event">
          <EventSwitcher />
          <span className="topbar__muted">Lagos, Nigeria</span>
          <span className="topbar__date">
            <CalendarIcon /> {fmtDay(event.focus.start)} – {fmtDay(event.focus.end)},{' '}
            {new Date(event.focus.start).getUTCFullYear()}
          </span>
        </div>
      )}
      <nav className="modes" aria-label="Mode">
        <button
          type="button"
          className={`mode${mode === 'sites' ? ' mode--active' : ''}`}
          aria-pressed={mode === 'sites'}
          onClick={() => setMode('sites')}
          title="The places that keep flooding across every flood on record."
        >
          <PinIcon />
          <span className="mode__wide">Places that flood</span>
          <span className="mode__narrow">Places</span>
        </button>
        <button
          type="button"
          className={`mode${mode === 'incident' ? ' mode--active' : ''}`}
          aria-pressed={mode === 'incident'}
          onClick={() => setMode('incident')}
          title="Replays a single flood hour by hour: rain, tide, radar and reports."
        >
          <MapIcon /> One flood
        </button>
      </nav>
      <div className="topbar__actions">
        <button
          className="topbar__action"
          onClick={copyLink}
          aria-live="polite"
          aria-label={copied ? 'Link copied' : 'Copy a link to this view'}
          title="Copy a link to this view"
        >
          <LinkIcon />
          <span className="topbar__action-label">{copied ? 'Link copied' : 'Copy link'}</span>
        </button>
        <button className="topbar__action" onClick={() => setHowOpen(true)} title="What the colours and words mean">
          <HelpIcon />
          <span className="topbar__action-label">How to read this</span>
        </button>
      </div>
      {howOpen && <HowToRead onClose={closeHowTo} />}
    </header>
  );
}
