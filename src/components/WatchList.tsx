import { useEffect, useMemo, useState } from 'react';
import { buildWatchList, type RainSummary } from '../lib/watchList';
import { loadRainSummary } from '../sites/load';
import type { SitePromise, SiteRecord } from '../sites/types';
import { useStore } from '../state/store';

/** Default as-of: 1 March of the current year if today is past it, else 1 March of last year. */
function defaultAsOf(today: Date): string {
  const march = (y: number) => `${y}-03-01`;
  return today >= new Date(`${march(today.getFullYear())}T00:00:00`) ? march(today.getFullYear()) : march(today.getFullYear() - 1);
}

/**
 * The pre-season watch list card (Task 32, LAGOS_PLAN roadmap step 8): one row per site with its tier and the three
 * tests, each tick or cross carrying its reason on hover or on expand. Sits above the site list; clicking a row opens
 * the site.
 */
export function WatchList({ sites, promises }: { sites: SiteRecord[]; promises: Record<string, SitePromise> }) {
  const selectSite = useStore((s) => s.selectSite);
  const [summary, setSummary] = useState<RainSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asOf, setAsOf] = useState(() => defaultAsOf(new Date()));
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    loadRainSummary()
      .then(setSummary)
      .catch((err: unknown) => setError(String(err)));
  }, []);

  const rows = useMemo(
    () => (summary ? buildWatchList(sites, promises, summary, new Date(`${asOf}T00:00:00`)) : []),
    [sites, promises, summary, asOf],
  );

  return (
    <section className="card">
      <header className="card__head">
        <h3>Pre-season watch list</h3>
        <label className="watch__asof">
          as of{' '}
          <input
            type="date"
            value={asOf}
            onChange={(e) => {
              if (e.target.value) setAsOf(e.target.value);
            }}
            aria-label="Watch list as-of date"
          />
        </label>
      </header>
      {!summary && !error && <p className="empty">Loading rain summary…</p>}
      {error && (
        <p className="empty">
          Could not load the rain summary: {error}{' '}
          <button className="link" onClick={() => useStore.getState().setSites(null)}>
            Retry
          </button>
        </p>
      )}
      {summary && (
        <ul className="watch">
          {rows.map((r) => (
            <li key={r.site_id}>
              <div className="watch__row">
                <button className="watch__open" onClick={() => selectSite(r.site_id)} title="Open this site">
                  <span className={`watch__tier watch__tier--${r.tier}`}>Tier {r.tier}</span>
                  <span className="watch__name">{r.name}</span>
                  {r.tests.map((t) => (
                    <span
                      key={t.key}
                      className={t.pass ? 'watch__tick' : 'watch__cross'}
                      title={`${t.label}: ${t.reason}`}
                    >
                      {t.pass ? '✓' : '✗'}
                    </span>
                  ))}
                </button>
                <button
                  className="watch__why"
                  onClick={() => setExpanded(expanded === r.site_id ? null : r.site_id)}
                  aria-expanded={expanded === r.site_id}
                >
                  {expanded === r.site_id ? 'hide reasons' : 'why?'}
                </button>
              </div>
              {expanded === r.site_id && (
                <ul className="watch__reasons">
                  {r.tests.map((t) => (
                    <li key={t.key}>
                      <b>{t.label}:</b> {t.reason}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="card__foot">Ranks sites by evidence on record, not by forecast. A site with no reports can still flood.</p>
    </section>
  );
}
