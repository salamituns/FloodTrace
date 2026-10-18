import { useMemo, useRef, useState, type PointerEvent } from 'react';
import type { KeyEventKind } from '../events/types';
import { fmtClock, fmtDateTime, fmtDay, localTicks } from '../lib/time';
import { useEvent, useStore } from '../state/store';
import { PauseIcon, PlayIcon, StepIcon } from './Icons';

export const KIND_COLORS: Record<KeyEventKind, string> = {
  documented: '#d4452f',
  satellite: '#1f6a9a',
  'tide-high': '#5f8fa6',
  'rain-onset': '#4a7fb5',
};

export function Timeline() {
  const event = useEvent();
  const t = useStore((s) => s.currentTime);
  const t0 = useStore((s) => s.t0);
  const t1 = useStore((s) => s.t1);
  const playing = useStore((s) => s.playing);
  const speed = useStore((s) => s.speed);
  const { setTime, togglePlay, cycleSpeed, setPlaying, selectEvent } = useStore.getState();
  const track = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const frac = (x: number) => (x - t0) / (t1 - t0);
  const ticks = useMemo(() => localTicks(t0, t1, 6), [t0, t1]);
  const visibleEvents = event.keyEvents.filter((e) => e.t >= t0 && e.t <= t1);

  const timeAt = (clientX: number) => {
    const r = track.current!.getBoundingClientRect();
    return t0 + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * (t1 - t0);
  };
  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    setPlaying(false);
    selectEvent(null);
    setTime(timeAt(e.clientX));
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    setHover(timeAt(e.clientX));
    if (e.currentTarget.hasPointerCapture(e.pointerId)) setTime(timeAt(e.clientX));
  };
  const stepToNextEvent = () => {
    const next = visibleEvents.find((ev) => ev.t > t + 60_000);
    setPlaying(false);
    if (next) {
      setTime(next.t);
      selectEvent(next.id);
    } else setTime(t1);
  };

  return (
    <section className="timeline">
      <header className="timeline__head">
        <h3>Timeline</h3>
        <span className="timeline__range">
          {fmtDateTime(t0)} – {fmtDateTime(t1)} (WAT)
        </span>
      </header>
      <div className="timeline__body">
        <div className="transport">
          <button className="icon-btn" onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
            {playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <button className="icon-btn" onClick={stepToNextEvent} aria-label="Next event">
            <StepIcon />
          </button>
          <button className="speed" onClick={cycleSpeed} title="Simulation hours per second">
            {speed}×
          </button>
        </div>
        <div className="scrubber">
          <div className="scrubber__track" ref={track} onPointerDown={onDown} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
            <div className="scrubber__rail" />
            <div className="scrubber__fill" style={{ width: `${frac(t) * 100}%` }} />
            {visibleEvents.map((ev) => (
              <span
                key={ev.id}
                className="scrubber__event"
                style={{ left: `${frac(ev.t) * 100}%`, color: KIND_COLORS[ev.kind] }}
                title={`${ev.name} · ${fmtDateTime(ev.t)}`}
              />
            ))}
            <div className="scrubber__thumb" style={{ left: `${frac(t) * 100}%` }}>
              <span className="scrubber__bubble">{fmtDateTime(t)}</span>
            </div>
            {hover !== null && (
              <span className="scrubber__hover" style={{ left: `${frac(hover) * 100}%` }}>
                {fmtDateTime(hover)}
              </span>
            )}
          </div>
          <div className="scrubber__ticks">
            {ticks.map((tick) => {
              const midnight = fmtClock(tick) === '00:00';
              return (
                <span key={tick} style={{ left: `${frac(tick) * 100}%` }}>
                  <b>{midnight || tick === ticks[0] ? fmtDay(tick) : ' '}</b>
                  {fmtClock(tick)}
                </span>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
