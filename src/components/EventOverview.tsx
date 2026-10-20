import { useState } from 'react';
import { fmtDateTime } from '../lib/time';
import { useEvent, useStore } from '../state/store';
import { ClampText } from './ClampText';
import { InfoTip } from './InfoTip';
import '../styles/flood.css';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Calendar date as "3 Jul 2024" — from YYYY-MM-DD, so timezone does not shift the day. */
function proseIso(iso: string): string {
  const [y, mo, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS[mo - 1]} ${y}`;
}

function peakReportIso(times: number[], timeZone: string): string | null {
  const counts = new Map<string, number>();
  for (const t of times) {
    const iso = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(t);
    counts.set(iso, (counts.get(iso) ?? 0) + 1);
  }
  let best: string | null = null;
  let n = 0;
  for (const [iso, c] of counts) {
    if (c > n) {
      best = iso;
      n = c;
    }
  }
  return best;
}

function mainDayIso(id: string, catalogDate: string | undefined, reportTimes: number[], timeZone: string): string {
  if (catalogDate && /^\d{4}-\d{2}-\d{2}$/.test(catalogDate)) return catalogDate;
  const fromId = id.match(/(\d{4}-\d{2}-\d{2})/);
  if (fromId) return fromId[1];
  return peakReportIso(reportTimes, timeZone) ?? 'unknown';
}

function placePhrase(areas: string[]): string {
  if (!areas.length) return 'across Lagos';
  if (areas.length === 1) return `in ${areas[0]}`;
  if (areas.length === 2) return `across ${areas[0]} and ${areas[1]}`;
  return `across ${areas[0]}, ${areas[1]} and the mainland`;
}

function leadCause(cause: string | null): string {
  if (!cause) return 'Flooding';
  if (/rain/i.test(cause)) return 'Heavy rain';
  if (/tide/i.test(cause)) return 'High water';
  return 'Flooding';
}

/** One-sentence answer, then main hours, likely cause, and what is still unknown. */
export function EventOverview() {
  const event = useEvent();
  const catalog = useStore((s) => s.catalog);
  const [techOpen, setTechOpen] = useState(false);
  const entry = catalog.find((c) => c.id === event.id);
  const areas = entry?.areas ?? [];
  const n = event.evidence.length;
  const reports = n === 1 ? '1 news report' : `${n} news reports`;
  const day = proseIso(mainDayIso(event.id, entry?.date, event.evidence.flatMap((e) => (e.t === null ? [] : [e.t])), event.timezone));
  const causeForLead = event.causePlain ?? event.causePrelim;
  const lead = `${leadCause(causeForLead)} on ${day} flooded roads ${placePhrase(areas)}; ${reports}.`;
  const cause = event.causePlain ?? event.causePrelim ?? 'Under investigation';
  const questions = event.openQuestionsPlain;
  const hasTech = Boolean(event.causePrelim) || event.openQuestions.length > 0;

  return (
    <section className="card">
      <header className="card__head">
        <h2>What happened</h2>
      </header>
      <p className="overview__lead">{lead}</p>
      <dl className="kv">
        <div>
          <dt>
            Main hours
            <InfoTip label="What Main hours means">The hours this replay covers.</InfoTip>
          </dt>
          <dd>
            {fmtDateTime(event.focus.start)} – {fmtDateTime(event.focus.end)}
          </dd>
        </div>
        <div>
          <dt>
            Likely cause
            <InfoTip label="What Likely cause means">Our first reading of what drove this flood.</InfoTip>
          </dt>
          <dd>
            <ClampText text={cause} className="reading__text" />
          </dd>
        </div>
      </dl>
      {questions.length > 0 && (
        <>
          <h3 className="subhead">Still unknown</h3>
          <ul className="questions">
            {questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      )}
      {hasTech && (
        <div className="tech-detail">
          <button
            type="button"
            className="tech-detail__toggle"
            aria-expanded={techOpen}
            onClick={() => setTechOpen((o) => !o)}
          >
            Technical detail {techOpen ? '▴' : '▾'}
          </button>
          {techOpen && (
            <div className="tech-detail__body">
              {event.causePrelim && <p>{event.causePrelim}</p>}
              {event.openQuestions.length > 0 && (
                <ul>
                  {event.openQuestions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
