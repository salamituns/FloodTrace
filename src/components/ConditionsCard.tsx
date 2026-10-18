import type { ReactNode } from 'react';
import { accumulate, sampleSeries } from '../events/load';
import { tidalLock } from '../lib/tidalLock';
import { HOUR, QUANT, fmtDateTime } from '../lib/time';
import { useEvent, useQuantTime, useStore } from '../state/store';
import { ArrowIcon, DropIcon, GaugeIcon, RainIcon, WaveIcon } from './Icons';

function Metric({ icon, label, value, unit, sub, danger }: { icon: ReactNode; label: string; value: string; unit: string; sub?: string; danger?: boolean }) {
  return (
    <div className={`metric ${danger ? 'metric--danger' : ''}`}>
      <span className="metric__icon">{icon}</span>
      <div>
        <div className="metric__label">{label}</div>
        <div className="metric__value">
          {value} <span className="metric__unit">{unit}</span>
        </div>
        {sub && <div className="metric__sub">{sub}</div>}
      </div>
    </div>
  );
}

const LOCK_TEXT = { none: 'No rain–tide conflict', watch: 'Watch: rain near high tide', likely: 'Likely tidal lock' } as const;

export function ConditionsCard() {
  const event = useEvent();
  const t = useQuantTime();
  const rainPoint = useStore((s) => s.rainPoint);
  const setRainPoint = useStore((s) => s.setRainPoint);
  const rain = event.rainfall.byPoint[rainPoint];

  const rainNow = sampleSeries(rain, t);
  const rain3h = accumulate(rain, t, 3);
  const rain24h = accumulate(rain, t, 24);
  const tide = sampleSeries(event.tide, t);
  const tideTrend = tide - sampleSeries(event.tide, t - HOUR);
  const lastPass = [...event.passes].reverse().find((p) => p.collection === 'SENTINEL-1' && p.t < t + QUANT);
  const reports = event.evidence.filter((e) => e.t !== null && e.t <= t).length;
  const lock = tidalLock({ rainMmH: rainNow || 0, rain3hMm: rain3h, tideM: tide || 0, tideTrendM: tideTrend || 0 });

  return (
    <section className="card">
      <header className="card__head">
        <h3>Conditions</h3>
        <select className="point-select" value={rainPoint} onChange={(e) => setRainPoint(e.target.value)} aria-label="Analysis point">
          {Object.keys(event.rainfall.byPoint).map((k) => (
            <option key={k} value={k}>
              {k.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </header>
      <div className={`lock lock--${lock}`}>{LOCK_TEXT[lock]}</div>
      <div className="metrics">
        <Metric icon={<RainIcon />} label="Rain now" value={Number.isNaN(rainNow) ? '–' : rainNow.toFixed(1)} unit="mm/h" danger={rainNow > 20} />
        <Metric icon={<DropIcon />} label="Last 3 h / 24 h" value={`${rain3h.toFixed(0)} / ${rain24h.toFixed(0)}`} unit="mm" />
        <Metric
          icon={<WaveIcon />}
          label="Tide (offshore)"
          value={Number.isNaN(tide) ? '–' : `${tide >= 0 ? '+' : ''}${tide.toFixed(2)}`}
          unit="m"
          sub={Number.isNaN(tideTrend) ? 'no data' : tideTrend > 0.02 ? 'rising' : tideTrend < -0.02 ? 'falling' : 'turning'}
        />
        <Metric icon={<GaugeIcon />} label="Reports so far" value={String(reports)} unit={`of ${event.evidence.length}`} />
        <Metric
          icon={<ArrowIcon />}
          label="Last radar pass"
          value={lastPass ? fmtDateTime(lastPass.t) : 'none yet'}
          unit=""
          sub={lastPass ? `${lastPass.platform} · track ${lastPass.relativeOrbit}` : undefined}
        />
      </div>
      <p className="card__foot">
        Rain: {event.rainfall.product}
        {event.rainfall.kind === 'reanalysis' && ' — smooths bursts; intensities understated'}
      </p>
    </section>
  );
}
