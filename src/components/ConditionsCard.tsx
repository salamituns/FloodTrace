import type { ReactNode } from 'react';
import { accumulate, sampleSeries } from '../events/load';
import { tidalLock } from '../lib/tidalLock';
import { HOUR, QUANT, fmtDateTime } from '../lib/time';
import { useEvent, useQuantTime, useStore } from '../state/store';
import { ArrowIcon, DropIcon, GaugeIcon, RainIcon, WaveIcon } from './Icons';
import '../styles/flood.css';

/** Title-case a point id the way the Read-at select shows it (Lekki, Lagos Island). */
export function pointDisplayName(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b[a-z]/g, (c) => c.toUpperCase());
}

function Metric({
  icon,
  label,
  value,
  unit,
  sub,
  danger,
  title,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  unit: string;
  sub?: string;
  danger?: boolean;
  title?: string;
}) {
  return (
    <div className={`metric ${danger ? 'metric--danger' : ''}`} title={title}>
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

const LOCK_TEXT = {
  none: "Tide was low while rain was heavy, so it wasn't holding water back.",
  watch: 'Rain near high tide: drains to the lagoon may empty more slowly.',
  likely: 'High tide during heavy rain: drains to the lagoon empty more slowly.',
} as const;

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
  const pointLabel = pointDisplayName(rainPoint);

  return (
    <section className="card">
      <header className="card__head">
        <h2>Right now</h2>
        <label className="toggle">
          Read at:
          <select
            className="point-select"
            value={rainPoint}
            onChange={(e) => setRainPoint(e.target.value)}
            aria-label="Read at this place"
            title="The spots the rain and tide charts read from. Not real gauges."
          >
            {Object.keys(event.rainfall.byPoint).map((k) => (
              <option key={k} value={k}>
                {pointDisplayName(k)}
              </option>
            ))}
          </select>
        </label>
      </header>
      <div className={`lock lock--${lock}`} title="When the tide is high, drains to the lagoon empty more slowly.">
        {LOCK_TEXT[lock]}
      </div>
      <div className="metrics">
        <Metric
          icon={<RainIcon />}
          label="Rain now"
          value={Number.isNaN(rainNow) ? '–' : rainNow.toFixed(1)}
          unit="mm/h"
          danger={rainNow > 20}
          title={`NASA GPM IMERG · ${pointLabel}`}
        />
        <Metric
          icon={<DropIcon />}
          label="Rain in the last 3 h / 24 h"
          value={`${rain3h.toFixed(0)} / ${rain24h.toFixed(0)}`}
          unit="mm"
          title={`NASA GPM IMERG · ${pointLabel}`}
        />
        <Metric
          icon={<WaveIcon />}
          label="Tide"
          value={Number.isNaN(tide) ? '–' : `${tide >= 0 ? '+' : ''}${tide.toFixed(2)}`}
          unit="m"
          sub={Number.isNaN(tideTrend) ? 'no data' : tideTrend > 0.02 ? 'rising' : tideTrend < -0.02 ? 'falling' : 'turning'}
          title="Modelled offshore tide (EOT20); no public lagoon gauge."
        />
        <Metric
          icon={<GaugeIcon />}
          label="News reports so far"
          value={`${reports} of ${event.evidence.length}`}
          unit=""
        />
        <Metric
          icon={<ArrowIcon />}
          label="Last radar pass"
          value={lastPass ? fmtDateTime(lastPass.t) : 'none yet'}
          unit=""
          sub={lastPass ? `${lastPass.platform} · track ${lastPass.relativeOrbit}` : undefined}
          title="Sentinel-1 radar pass"
        />
      </div>
    </section>
  );
}
