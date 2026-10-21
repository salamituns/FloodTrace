/**
 * Unit checks for src/lib/forecast.ts (Task 41, docs/tasks/41-forecast-ui.md).
 *
 *   npx tsx scripts/check-forecast.ts
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
	analoguesLine,
	cellIdAt,
	citywideHeadline,
	comingUpHeadline,
	forecastFreshness,
	forecastUrl,
	impactsLine,
	licenceFootnote,
	mappedFloodId,
	pct40,
	pctChance,
	whatToDo,
	windowStartPhrase,
	type ForecastDay,
	type ForecastFile,
	type ImpactsSummary,
} from '../src/lib/forecast';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

let failed = 0;
function check(ok: boolean, msg: string): void {
	console.log(`${ok ? 'ok' : 'FAIL'} - ${msg}`);
	if (!ok) failed += 1;
}

function day(over: Partial<ForecastDay> & Pick<ForecastDay, 'date' | 'level'>): ForecastDay {
	return {
		rain: {
			median_mm: 4,
			p90_mm: 12,
			chance_ge_20mm: 0.02,
			chance_ge_40mm: 0.02,
			chance_ge_60mm: 0,
			peak_3h: { start_hour_local: '15:00', median_mm: 1, p90_mm: 3 },
			second_opinion_gfs: { median_mm: 0, p90_mm: 1, chance_ge_40mm: 0 },
		},
		risk: { hours: [], near_high_tide: false },
		level_reason: '',
		...over,
	};
}

const heavyThu = day({
	date: '2026-10-22',
	level: 'high',
	rain: {
		median_mm: 52,
		p90_mm: 80,
		chance_ge_20mm: 0.7,
		chance_ge_40mm: 0.41,
		chance_ge_60mm: 0.2,
		peak_3h: { start_hour_local: '14:00', median_mm: 28, p90_mm: 40 },
		second_opinion_gfs: { median_mm: 40, p90_mm: 60, chance_ge_40mm: 0.3 },
	},
	risk: { hours: [{ start: '2026-10-22T14:00', end: '2026-10-22T19:00' }], near_high_tide: true },
});

// ── cell snap (IMERG 0.1° centres at x.x5) ───────────────────────────────
check(cellIdAt(3.36, 6.51) === 'c6.55N3.35E', 'Ojuelegba snaps to c6.55N3.35E');
check(cellIdAt(3.518, 6.447) === 'c6.45N3.55E', 'Agungi snaps to c6.45N3.55E');

// ── headline ─────────────────────────────────────────────────────────────
check(
	comingUpHeadline([heavyThu]) ===
		'Heavy rain likely Thursday afternoon (14:00–19:00), close to high tide.',
	'high-day headline uses window + tide',
);
check(
	comingUpHeadline([day({ date: '2026-10-21', level: 'none' })]) ===
		'No heavy rain in the forecast for the next 7 days.',
	'quiet-week headline',
);
check(
	comingUpHeadline([
		day({ date: '2026-10-21', level: 'none' }),
		day({
			date: '2026-10-24',
			level: 'medium',
			risk: { hours: [{ start: '2026-10-24T08:00', end: '2026-10-24T11:00' }], near_high_tide: false },
			rain: {
				median_mm: 30,
				p90_mm: 50,
				chance_ge_20mm: 0.5,
				chance_ge_40mm: 0.15,
				chance_ge_60mm: 0,
				peak_3h: { start_hour_local: '08:00', median_mm: 12, p90_mm: 20 },
				second_opinion_gfs: { median_mm: 20, p90_mm: 30, chance_ge_40mm: 0.1 },
			},
		}),
	]) === 'Heavy rain possible Saturday morning (08:00–11:00).',
	'medium-day headline, no tide clause',
);

// ── freshness ────────────────────────────────────────────────────────────
const made = '2026-10-21T18:31:20+00:00';
const fresh = forecastFreshness(made, Date.parse('2026-10-21T20:00:00+00:00'));
check(!fresh.stale, 'run from two hours ago is fresh');
check(
	fresh.madeLine === 'Forecast made Wednesday, 19:31 (Lagos time)',
	`fresh line: ${fresh.madeLine}`,
);
const stale = forecastFreshness(made, Date.parse('2026-10-23T08:00:00+00:00'));
check(stale.stale, 'run older than 36 hours is stale');
check(
	stale.madeLine === 'This forecast is out of date (made 21 Oct 2026)',
	`stale line: ${stale.madeLine}`,
);

check(pct40(0.41) === '40 mm+: 41% chance', 'chance label');
check(pctChance(0.02) === '2%', 'week-strip chance is the percent only');
check(
	analoguesLine(41, 7) ===
		'Of 41 past days with similar rain here, 7 had floods reported within 5 km.',
	'local analogue count, not citywide',
);

check(windowStartPhrase(heavyThu) === '14:00 on Thursday', 'action window start');
check(
	whatToDo('none', null, []).join('|') === "Nothing to do yet. Forecasts often miss Lagos downpours, so if heavy rain starts, move valuables off the floor and keep off flooded roads.",
	'quiet what-to-do is one line',
);
const highDo = whatToDo('high', '14:00 on Thursday', ['Ikorodu Road', 'Fashoro Street']);
check(highDo[0] === 'Move valuables and documents off the floor before 14:00 on Thursday.', 'high: valuables');
check(highDo.some((s) => s.includes('Avoid Ikorodu Road and Fashoro Street during the window.')), 'high: roads');
check(highDo.some((s) => s.includes("you can't see how deep it is or what is under it")), 'high: flood water');
check(highDo.some((s) => s.includes('Check on neighbours who may need help.')), 'high: neighbours');
// No emergency numbers: none could be confirmed on an official Lagos State or LASEMA page.
check(!highDo.some((s) => s.includes('767')), 'high: no unconfirmed emergency numbers');

const impacts: ImpactsSummary = {
	roads: [{ name: 'Ikorodu Road', lengthUnderWaterM: 400 }, { name: 'Fashoro Street', lengthUnderWaterM: 80 }],
	facilities: [{ name: 'St Agnes', kind: 'school' }],
	buildings: 12,
};
check(
	impactsLine(impacts) ===
		'Roads in spots reported flooded nearby: Ikorodu Road, Fashoro Street. Near a school: St Agnes. About 12 mapped buildings sit inside those spots (their edges are rough).',
	`impacts line: ${impactsLine(impacts)}`,
);

check(mappedFloodId('2024-07-03', ['lagos-2024-07-03']) === 'lagos-2024-07-03', 'mapped flood replay id');
check(mappedFloodId('2018-06-01', ['lagos-2024-07-03']) === null, 'unmapped analogue has no replay');

const cityQuiet: Pick<ForecastFile, 'citywide' | 'meta'> = {
	meta: { run: { generated_at: made }, sources: [] } as ForecastFile['meta'],
	citywide: {
		days: ['2026-10-21', '2026-10-22', '2026-10-23', '2026-10-24', '2026-10-25', '2026-10-26', '2026-10-27'].map(
			(date) => ({
				date,
				overall_level: 'none' as const,
				cells_by_level: { high: 0, medium: 0, low: 0, none: 68 },
				most_at_risk: [],
			}),
		),
	},
};
const quiet = citywideHeadline(cityQuiet as ForecastFile, Date.parse('2026-10-21T20:00:00+00:00'));
check(quiet.quiet, 'citywide quiet flag');
check(
	quiet.text === 'No heavy rain in the forecast for Lagos in the next 7 days (forecast made Wednesday, 19:31).',
	`quiet citywide: ${quiet.text}`,
);

const foot = licenceFootnote({
	sources: [
		{ name: 'Open-Meteo Ensemble API, ECMWF IFS 0.25 deg ensemble', licence: 'CC BY 4.0 (attribution required); ECMWF IFS data (c) ECMWF', url: '', note: '' },
		{ name: 'EOT20 global ocean tide model', licence: 'CC BY 4.0', url: '', note: '' },
	],
} as ForecastFile['meta']);
check(
	foot.includes(
		'ECMWF IFS © ECMWF, GFS © NOAA, GloFAS © Copernicus CEMS, all CC BY 4.0 via Open-Meteo; NASA IMERG open data; news reports compiled by FloodTrace.',
	),
	'footnote has one tidy licence line',
);
check(!foot.includes('attribution required'), 'no repeated CC BY 4.0 attribution clause');

check(forecastUrl(false, '?forecast=fixture') === '/events/forecast/latest.json', 'fixture query is a no-op outside DEV');
check(forecastUrl(true, '?forecast=fixture') === '/events/forecast/_fixture_storm.json', 'DEV loads the fixture');
check(forecastUrl(true, '') === '/events/forecast/latest.json', 'DEV default is latest.json');

const latest = JSON.parse(readFileSync(path.join(root, 'events/forecast/latest.json'), 'utf8')) as ForecastFile;
const allNone = Object.values(latest.cells).every((c) => c.days.every((d) => d.level === 'none'));
check(allNone, 'this week is quiet: every cell-day is none');
const hourly = Object.values(latest.cells)[0].hourly;
check(!!hourly && hourly.median.length === 168 && hourly.p90.length === 168, 'hourly export is 168 hours');
check(forecastUrl(false, '?forecast=fixture') === '/events/forecast/latest.json', 'production ignores ?forecast=fixture');

if (failed) {
	console.log(`\n${failed} check(s) failed`);
	process.exit(1);
}
console.log('\nall forecast checks passed');
