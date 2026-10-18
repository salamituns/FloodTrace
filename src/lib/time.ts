// All clock values are epoch ms; display uses the active event's IANA timezone.
export const HOUR = 3_600_000;

// UI panels that don't need frame-accurate time re-render on this grid.
export const QUANT = 15 * 60_000;

let zone = 'Africa/Lagos';
let dayFmt: Intl.DateTimeFormat;
let clockFmt: Intl.DateTimeFormat;
let zoneFmt: Intl.DateTimeFormat;

export function setTimeZone(tz: string): void {
  zone = tz;
  dayFmt = new Intl.DateTimeFormat('en-US', { timeZone: zone, month: 'short', day: 'numeric' });
  clockFmt = new Intl.DateTimeFormat('en-GB', { timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  zoneFmt = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'short' });
}
setTimeZone(zone);

export const fmtDay = (t: number) => dayFmt.format(t);

/** Offset of the event timezone from UTC at instant t, in ms (e.g. +1 h for Lagos). */
export function zoneOffsetMs(t: number): number {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' })
      .formatToParts(t)
      .map((x) => [x.type, x.value]),
  );
  const wall = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
  return wall - Math.floor(t / 60_000) * 60_000;
}

/** Instants in [t0, t1] that fall on local-time multiples of `stepH` hours (00:00, 06:00, …). */
export function localTicks(t0: number, t1: number, stepH: number): number[] {
  const step = stepH * HOUR;
  const off = zoneOffsetMs(t0);
  const out: number[] = [];
  for (let x = Math.ceil((t0 + off) / step) * step - off; x <= t1; x += step) out.push(x);
  return out;
}
export const fmtClock = (t: number) => clockFmt.format(t);
export const fmtDateTime = (t: number) => `${fmtDay(t)}, ${fmtClock(t)}`;
export const zoneLabel = (t: number) => zoneFmt.formatToParts(t).find((p) => p.type === 'timeZoneName')?.value ?? zone;

/** Parse "2024-07-03T02:00" (local wall time with no offset) using a fixed UTC offset in seconds. */
export const parseLocal = (s: string, offsetSec: number) => Date.parse(`${s}Z`) - offsetSec * 1000;
