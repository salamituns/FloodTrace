import { useMemo, useState, type ReactElement } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { sampleSeries } from '../events/load';
import { HOUR, fmtClock, fmtDay, localTicks } from '../lib/time';
import { useEvent, useQuantTime, useStore } from '../state/store';
import { pointDisplayName } from './ConditionsCard';
import '../styles/flood.css';

const AXIS = { fontSize: 10, fill: '#5d574e' };
const tickLabel = (t: number) => (fmtClock(t) === '00:00' ? fmtDay(t) : fmtClock(t));

function ChartCard({ heading, title, children }: { heading: string; title?: string; children: ReactElement }) {
  return (
    <section className="chart">
      <header className="chart__head">
        <h3 title={title}>{heading}</h3>
      </header>
      <div className="chart__body">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export function Charts() {
  const event = useEvent();
  const t = useQuantTime();
  const t0 = useStore((s) => s.t0);
  const t1 = useStore((s) => s.t1);
  const rainPoint = useStore((s) => s.rainPoint);
  const [open, setOpen] = useState(() =>
    typeof window === 'undefined'
      ? true
      : window.matchMedia('(min-width: 721px) and (min-height: 820px)').matches,
  );
  const domain: [number, number] = [t0, t1];
  const ticks = useMemo(() => localTicks(t0, t1, 12), [t0, t1]);
  const xAxis = <XAxis dataKey="t" type="number" domain={domain} ticks={ticks} tickFormatter={tickLabel} tick={AXIS} tickLine={false} axisLine={{ stroke: '#d6d0c5' }} allowDataOverflow />;
  const place = pointDisplayName(rainPoint);

  const rain = useMemo(() => {
    const s = event.rainfall.byPoint[rainPoint];
    return s.t.map((x, i) => ({ t: x, v: s.v[i] })).filter((d) => d.t >= t0 && d.t <= t1);
  }, [event, rainPoint, t0, t1]);

  const tide = useMemo(
    () =>
      event.tide.t
        .map((x, i) => ({ t: x, v: event.tide.v[i] }))
        .filter((d) => d.t >= t0 - HOUR && d.t <= t1 + HOUR)
        .map((d) => ({ t: d.t, past: d.t <= t + HOUR ? d.v : null, future: d.t >= t - HOUR ? d.v : null })),
    [event, t0, t1, t],
  );

  const reports = useMemo(() => {
    const bins: { t: number; n: number }[] = [];
    for (let x = t0; x < t1; x += 3 * HOUR) bins.push({ t: x + 1.5 * HOUR, n: 0 });
    for (const e of event.evidence) {
      if (e.t === null || e.t < t0 || e.t >= t1) continue;
      bins[Math.floor((e.t - t0) / (3 * HOUR))].n++;
    }
    return bins;
  }, [event, t0, t1]);

  return (
    <div className={`charts${open ? '' : ' is-folded'}`}>
      <button type="button" className="charts__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        Charts {open ? '▾' : '▸'}
      </button>
      {open && (
        <>
          <ChartCard
            heading={`Rain at ${place} (mm per hour)`}
            title={event.rainfall.kind === 'imerg' ? 'NASA GPM IMERG, 30-min, ~10 km cells.' : 'ERA5 reanalysis — smooths bursts; intensities understated'}
          >
            <BarChart data={rain} margin={{ top: 6, right: 10, bottom: 0, left: -18 }} barCategoryGap={1}>
              <CartesianGrid vertical={false} stroke="#ece7de" />
              {xAxis}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Bar dataKey="v" isAnimationActive={false}>
                {rain.map((d) => (
                  <Cell key={d.t} fill={d.t <= t ? '#4a7fb5' : '#c9d8e6'} />
                ))}
              </Bar>
              <ReferenceLine x={t} stroke="#2b2824" />
            </BarChart>
          </ChartCard>

          <ChartCard heading="Tide (m)" title="Modelled offshore tide (EOT20); no public lagoon gauge.">
            <LineChart data={tide} margin={{ top: 6, right: 10, bottom: 0, left: -18 }}>
              <CartesianGrid vertical={false} stroke="#ece7de" />
              {xAxis}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} />
              <ReferenceLine y={0} stroke="#d6d0c5" />
              <Line dataKey="future" stroke="#9db6c8" strokeDasharray="3 3" dot={false} isAnimationActive={false} connectNulls={false} />
              <Line dataKey="past" stroke="#1f5f8b" strokeWidth={1.8} dot={false} isAnimationActive={false} connectNulls={false} />
              <ReferenceLine x={t} stroke="#2b2824" />
              <ReferenceDot x={t} y={sampleSeries(event.tide, t)} r={3.5} fill="#fff" stroke="#2b2824" />
            </LineChart>
          </ChartCard>

          <ChartCard heading="News reports per 3 hours" title={event.evidence.length ? `${event.evidence.length} reports in this flood` : 'none yet'}>
            <BarChart data={reports} margin={{ top: 6, right: 10, bottom: 0, left: -18 }} barCategoryGap={2}>
              <CartesianGrid vertical={false} stroke="#ece7de" />
              {xAxis}
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} allowDecimals={false} />
              <Bar dataKey="n" isAnimationActive={false}>
                {reports.map((d) => (
                  <Cell key={d.t} fill={d.t <= t ? '#d4452f' : '#f0c9bf'} />
                ))}
              </Bar>
              <ReferenceLine x={t} stroke="#2b2824" />
            </BarChart>
          </ChartCard>
        </>
      )}
    </div>
  );
}
