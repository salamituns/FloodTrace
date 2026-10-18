/** Official drainage promises and how the app judges whether they were kept (docs/SITES_PLAN.md). */

export type PromiseKind = 'build' | 'expand' | 'excavate' | 'dredge' | 'demolish' | 'enforce' | 'maintain' | 'other';
export type PromiseStatus = 'delivered' | 'in_progress' | 'stalled' | 'no_visible_work' | 'overdue' | 'unverifiable';

export interface PromiseUpdate {
  date: string; // ISO date
  kind: 'news' | 'official' | 'imagery';
  ref: string;
  /** What this update shows about the promise. */
  finding: 'done' | 'work_seen' | 'no_change' | 'claimed_done' | 'claimed_ongoing';
  /** Reviewer's description of what the image or report shows. */
  note?: string;
}

export interface OfficialPromise {
  promise_id: string;
  site_id: string;
  made_by: string;
  date_made: string;
  kind: PromiseKind;
  what: string;
  quote: string;
  url: string;
  due: { date: string | null; basis: 'stated' | 'contract' | 'inferred' | 'none'; note?: string };
  updates: PromiseUpdate[]; // oldest first
}

/** Months after which a promise with no stated due date counts as late. Used only when due.date is null. */
export const DEFAULT_GRACE_MONTHS = 12;
/** Work last seen longer ago than this is stalled, not in progress. */
export const STALE_MONTHS = 12;
/** Work that can't be seen from space; claims about it can never be checked by imagery. */
const INVISIBLE_KINDS: PromiseKind[] = ['dredge', 'maintain'];

const addMonths = (iso: string, m: number) => {
  const d = new Date(iso);
  d.setMonth(d.getMonth() + m);
  return d;
};

/**
 * Decides a promise's status from imagery alone (the user's rule): an official's "done" or "ongoing" is recorded
 * but never changes the status. Order: invisible kind → delivered → no imagery → overdue → in progress / stalled
 * → no visible work.
 */
export function promiseStatus(p: OfficialPromise, today: Date): PromiseStatus {
  if (INVISIBLE_KINDS.includes(p.kind)) return 'unverifiable';
  const seen = p.updates.filter((u) => u.kind === 'imagery' && u.date >= p.date_made);
  if (seen.some((u) => u.finding === 'done')) return 'delivered';
  if (seen.length === 0) return 'unverifiable';
  const due = p.due.date ? new Date(p.due.date) : addMonths(p.date_made, DEFAULT_GRACE_MONTHS);
  if (today > due) return 'overdue';
  const work = seen.filter((u) => u.finding === 'work_seen');
  const lastWork = work[work.length - 1];
  if (!lastWork) return 'no_visible_work';
  return addMonths(lastWork.date, STALE_MONTHS) < today ? 'stalled' : 'in_progress';
}
