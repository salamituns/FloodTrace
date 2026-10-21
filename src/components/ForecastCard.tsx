import { useEffect, useMemo, useState } from 'react';
import {
	analoguesLine,
	cellContaining,
	LEVEL_RANK,
	citywideHeadline,
	comingUpHeadline,
	forecastFreshness,
	fmtOn,
	impactsLine,
	licenceFootnote,
	loadForecast,
	mappedFloodId,
	whatToDo,
	windowStartPhrase,
	weekdayShort,
	type ForecastFile,
} from '../lib/forecast';
import { impactsAt } from '../lib/impacts';
import { useStore } from '../state/store';
import { WeekStrip, weekDaysFrom } from './WeekStrip';
import '../styles/forecast.css';

function preferReducedMotion(): boolean {
	return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function hourStamp(runDate: string, i: number): string {
	const [y, m, d] = runDate.split('-').map(Number);
	const utc = Date.UTC(y, m - 1, d + Math.floor(i / 24));
	const iso = new Date(utc).toISOString().slice(0, 10);
	const hh = i % 24;
	return `${iso}T${hh < 10 ? `0${hh}` : hh}:00`;
}

function Play48({
	file,
	dayIndex,
}: {
	file: ForecastFile;
	dayIndex: number;
}) {
	const setForecastHour = useStore((s) => s.setForecastHour);
	const hour = useStore((s) => s.forecastHour);
	const reduce = preferReducedMotion();
	const [playing, setPlaying] = useState(false);
	const start = dayIndex * 24;
	const end = Math.min(start + 48, 168) - 1;
	const tides = useMemo(() => new Set(file.tides.high_tides.map((t) => t.time)), [file]);

	useEffect(() => {
		if (!playing || reduce) return;
		const id = window.setInterval(() => {
			const cur = useStore.getState().forecastHour;
			const next = cur === null || cur >= end ? start : cur + 1;
			setForecastHour(next);
			if (next >= end) setPlaying(false);
		}, 400);
		return () => window.clearInterval(id);
	}, [playing, reduce, start, end, setForecastHour]);

	useEffect(() => () => setForecastHour(null), [setForecastHour, dayIndex]);

	const h = hour ?? start;
	const stamp = hourStamp(file.meta.run.run_date, h);
	const tide = tides.has(stamp) || tides.has(`${stamp.slice(0, 16)}`);
	const label = `${weekdayShort(stamp.slice(0, 10))} ${stamp.slice(11, 16)}${tide ? ' · high tide' : ''}`;

	return (
		<div className="forecast-playbar">
			{reduce ? (
				<>
					<button type="button" className="forecast-play" onClick={() => setForecastHour(Math.max(start, h - 1))}>
						Previous hour
					</button>
					<button type="button" className="forecast-play" onClick={() => setForecastHour(Math.min(end, h + 1))}>
						Next hour
					</button>
				</>
			) : (
				<button
					type="button"
					className="forecast-play"
					onClick={() => {
						if (!playing && hour === null) setForecastHour(start);
						setPlaying((p) => !p);
					}}
				>
					{playing ? 'Pause' : 'Play the next 48 hours'}
				</button>
			)}
			<input
				type="range"
				min={start}
				max={end}
				value={h}
				aria-label="Forecast hour"
				onChange={(e) => setForecastHour(Number(e.target.value))}
			/>
			<span className="forecast-playbar__time">{label}</span>
		</div>
	);
}

export function ForecastCard({ lon, lat }: { lon: number; lat: number }) {
	const [file, setFile] = useState<ForecastFile | null>(null);
	const catalog = useStore((s) => s.catalog);
	const forecastDay = useStore((s) => s.forecastDay);
	const selectForecastDay = useStore((s) => s.selectForecastDay);
	const clearForecastLayer = useStore((s) => s.clearForecastLayer);
	const setForecastHighlightDate = useStore((s) => s.setForecastHighlightDate);
	const requestShowMe3D = useStore((s) => s.requestShowMe3D);
	const [impactsText, setImpactsText] = useState<string | null>(null);
	const [hitRoads, setHitRoads] = useState<string[]>([]);

	useEffect(() => {
		loadForecast().then(setFile);
	}, []);

	const cell = file ? cellContaining(file, lon, lat) : null;
	const fresh = file ? forecastFreshness(file.meta.run.generated_at) : null;
	const selected = cell?.days.find((d) => d.date === forecastDay) ?? null;
	const worst = useMemo(() => {
		if (!cell) return null;
		return [...cell.days].sort((a, b) => LEVEL_RANK[b.level] - LEVEL_RANK[a.level])[0];
	}, [cell]);
	const focus = selected ?? (worst && (worst.level === 'medium' || worst.level === 'high') ? worst : null);

	useEffect(() => {
		if (!focus || (focus.level !== 'medium' && focus.level !== 'high')) {
			setImpactsText(null);
			setHitRoads([]);
			return;
		}
		let dead = false;
		impactsAt(lon, lat, 1500, 'evidence')
			.then((imp) => {
				if (dead) return;
				setImpactsText(impactsLine(imp));
				setHitRoads([...new Set(imp.roads.map((r) => r.name))].slice(0, 6));
			})
			.catch(() => {
				if (dead) return;
				setImpactsText(null);
				setHitRoads([]);
			});
		return () => {
			dead = true;
		};
	}, [lon, lat, focus]);

	if (!file || !cell || !fresh) return null;

	const headline = comingUpHeadline(cell.days);
	const analogue = focus?.analogues;
	const topDays = analogue?.days.slice(0, 3) ?? [];
	const catalogIds = catalog.filter((c) => c.built).map((c) => c.id);
	const todo = focus
		? whatToDo(focus.level, windowStartPhrase(focus), hitRoads)
		: whatToDo(worst?.level ?? 'none', worst ? windowStartPhrase(worst) : null, []);

	const dayIndex = cell.days.findIndex((d) => d.date === (selected ?? focus)?.date);

	return (
		<section className="card">
			<h3>Coming up</h3>
			<p className="area-answer">{headline}</p>
			<p className={`forecast-made${fresh.stale ? ' forecast-made--stale' : ''}`}>{fresh.madeLine}</p>
			<WeekStrip
				days={weekDaysFrom(cell.days)}
				selected={forecastDay}
				stale={fresh.stale}
				onSelect={selectForecastDay}
				onClear={clearForecastLayer}
			/>
			{focus && (focus.level === 'medium' || focus.level === 'high') && analogue && (
				<>
					<h4>Past storms like this here</h4>
					<p className="area-answer">{analoguesLine(analogue.n_qualifying, analogue.n_qualifying_flood_days)}</p>
					<ul className="forecast-analogues">
						{topDays.map((a, i) => (
							<li key={a.date}>
								<b>{fmtOn(a.date)}</b>
								<small>
									{a.imerg_mm} mm
									{a.areas_within_5km.length ? ` · ${a.areas_within_5km.map((x) => x.name).join(', ')}` : ''}
								</small>
								{i === 0 && (
									<div className="forecast-actions">
										<button
											type="button"
											className="link"
											onClick={() => {
												setForecastHighlightDate(a.date);
												requestShowMe3D(lon, lat);
											}}
										>
											Show me last time
										</button>
										{mappedFloodId(a.date, catalogIds) && (
											<button
												type="button"
												className="link"
												onClick={() => {
													const url = new URL(location.href);
													url.searchParams.set('event', mappedFloodId(a.date, catalogIds)!);
													url.hash = '';
													location.assign(url.toString());
												}}
											>
												Replay this flood →
											</button>
										)}
									</div>
								)}
							</li>
						))}
					</ul>
					{impactsText && (
						<>
							<h4>What was in the water before</h4>
							<p className="area-answer">{impactsText}</p>
						</>
					)}
				</>
			)}
			<h4>What to do</h4>
			{todo.length === 1 ? (
				<p className="area-answer">{todo[0]}</p>
			) : (
				<ul className="forecast-todo">
					{todo.map((line) => (
						<li key={line}>{line}</li>
					))}
				</ul>
			)}
			{selected && dayIndex >= 0 && <Play48 file={file} dayIndex={dayIndex} />}
			<p className="card__foot">{licenceFootnote(file.meta)}</p>
		</section>
	);
}

export function ThisWeekCard() {
	const [file, setFile] = useState<ForecastFile | null>(null);
	const forecastDay = useStore((s) => s.forecastDay);
	const selectForecastDay = useStore((s) => s.selectForecastDay);
	const clearForecastLayer = useStore((s) => s.clearForecastLayer);
	const focusStreetSearch = useStore((s) => s.focusStreetSearch);

	useEffect(() => {
		loadForecast().then(setFile);
	}, []);

	if (!file) return null;
	const fresh = forecastFreshness(file.meta.run.generated_at);
	const city = citywideHeadline(file);
	if (city.quiet) return <p className="this-week--quiet">{city.text}</p>;

	return (
		<section className="card this-week">
			<h3>This week</h3>
			<p className="area-answer">{city.text}</p>
			<p className={`forecast-made${fresh.stale ? ' forecast-made--stale' : ''}`}>{fresh.madeLine}</p>
			<WeekStrip
				days={file.citywide.days.map((d) => ({
					date: d.date,
					level: d.overall_level,
					chance_ge_40mm: Math.max(0, ...d.most_at_risk.map((x) => x.chance_ge_40mm)),
				}))}
				selected={forecastDay}
				stale={fresh.stale}
				onSelect={selectForecastDay}
				onClear={clearForecastLayer}
			/>
			<button type="button" className="this-week__check" onClick={focusStreetSearch}>
				Check your street →
			</button>
		</section>
	);
}
