import { countCauses } from '../lib/causes';
import { fmtDateTime } from '../lib/time';
import { useEvent } from '../state/store';

/** What we know about the event and how well each dataset covers it. */
export function EventOverview() {
  const event = useEvent();
  const s1 = event.passes.filter((p) => p.collection === 'SENTINEL-1' && p.t >= event.window.start && p.t <= event.window.end);
  const s2Clear = event.passes.filter((p) => p.collection === 'SENTINEL-2' && (p.cloudCover ?? 100) < 30);
  const read = event.evidence.filter((e) => e.props.read_status === 'read').length;
  const causes = countCauses(event.evidence, event.citywideCauses);
  const maxCause = Math.max(1, ...causes.map((c) => c.total));

  const rows: [string, string, 'ok' | 'warn' | 'gap'][] = [
    ['Rainfall', event.rainfall.kind === 'imerg' ? 'IMERG 30-min' : 'ERA5 hourly (context only)', event.rainfall.kind === 'imerg' ? 'ok' : 'warn'],
    ['Tide', event.tide.t.length ? `${event.tideProduct}, offshore, hourly` : 'No model data for this period', event.tide.t.length ? 'warn' : 'gap'],
    ['Radar (S1)', event.sar ? `During-event pass ${fmtDateTime(event.sar.observedAt)}` : s1.length ? `${s1.length} passes, none processed` : 'None (Sentinel-1 launched 2014)', event.sar ? 'ok' : 'gap'],
    ['Optical (S2)', s2Clear.length ? `${s2Clear.length} clear scenes` : 'All scenes cloud-covered', s2Clear.length ? 'ok' : 'gap'],
    ['Media evidence', event.evidence.length ? `${event.evidence.length} reports (${read} read in full)` : 'Not collected yet', event.evidence.length ? 'ok' : 'gap'],
    ['Drainage', `${event.drainage.features.length.toLocaleString()} OSM features; state network not public`, 'warn'],
  ];

  return (
    <section className="card">
      <header className="card__head">
        <h3>Event Overview</h3>
        <span className="card__hint">{event.id}</span>
      </header>
      <dl className="kv">
        <div>
          <dt>Focus window</dt>
          <dd>
            {fmtDateTime(event.focus.start)} – {fmtDateTime(event.focus.end)}
          </dd>
        </div>
        <div>
          <dt>Cause (prelim.)</dt>
          <dd>{event.causePrelim ?? 'Under investigation'}</dd>
        </div>
      </dl>
      {event.openQuestions.length > 0 && (
        <>
          <h4 className="subhead">Open questions</h4>
          <ul className="questions">
            {event.openQuestions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      )}
      {causes.length > 0 && (
        <>
          <h4 className="subhead">Reported causes</h4>
          <ul className="causes">
            {causes.map((c) => (
              <li key={c.tag}>
                <span>{c.label}</span>
                <span className="causes__n">
                  {c.total} {c.official > 0 && `· ${c.official} official`}
                </span>
                <span className={`causes__bar${c.human ? ' causes__bar--human' : ''}`} style={{ width: `${(c.total / maxCause) * 100}%` }} />
              </li>
            ))}
          </ul>
          <p className="causes__note">What sources blamed, not a verdict. Brown = human factors.</p>
        </>
      )}
      <h4 className="subhead">Evidence coverage</h4>
      <ul className="coverage">
        {rows.map(([k, v, level]) => (
          <li key={k}>
            <span className={`dot dot--${level}`} />
            <span className="coverage__k">{k}</span>
            <span className="coverage__v">{v}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
