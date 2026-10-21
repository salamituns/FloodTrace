/** 7-day flood-risk forecast helpers (Task 41).
 *
 * The pipeline writes events/forecast/latest.json; this module loads it once,
 * finds the IMERG cell for a lon/lat, and turns a cell-day into the plain
 * sentences on the Coming-up card. Numbers on screen always come from the
 * file — never invented.
 */

export type ForecastLevel = 'none' | 'low' | 'medium' | 'high';

export const LEVEL_RANK: Record<ForecastLevel, number> = { none: 0, low: 1, medium: 2, high: 3 };
export const LEVEL_WORD: Record<ForecastLevel, string> = {
	none: 'None',
	low: 'Low',
	medium: 'Medium',
	high: 'High',
};

/** Badge colours matching places__prio (High / Medium / Low / Lowest). */
export const LEVEL_RGB: Record<ForecastLevel, [number, number, number]> = {
	high: [163, 54, 31],
	medium: [185, 123, 16],
	low: [93, 87, 78],
	none: [154, 147, 133],
};

export interface ForecastHours {
	start: string;
	end: string;
}

export interface ForecastDay {
	date: string;
	rain: {
		median_mm: number;
		p90_mm: number;
		chance_ge_20mm: number;
		chance_ge_40mm: number;
		chance_ge_60mm: number;
		peak_3h: { start_hour_local: string; median_mm: number; p90_mm: number };
		second_opinion_gfs: { median_mm: number; p90_mm: number; chance_ge_40mm: number };
	};
	risk: { hours: ForecastHours[]; near_high_tide: boolean };
	level: ForecastLevel;
	level_reason: string;
	analogues?: {
		n_qualifying: number;
		n_qualifying_flood_days: number;
		n_qualifying_citywide_flood_days: number;
		days: {
			date: string;
			imerg_mm: number;
			flood_day: boolean;
			citywide_flood_day: boolean;
			areas_within_5km: { name: string; lon: number; lat: number }[];
		}[];
	};
}

export interface ForecastCell {
	centre: { lon: number; lat: number; place: string | null };
	days: ForecastDay[];
	hourly?: { median: number[]; p90: number[] };
}

export interface ForecastFile {
	meta: {
		run: { run_date: string; generated_at: string; forecast_days: string[] };
		sources: { name: string; url: string; licence: string; note: string }[];
		models: { rain_headline: string; tide: string };
		caveats: string[];
	};
	tides: { high_tides: { time: string; height_m: number }[] };
	cells: Record<string, ForecastCell>;
	citywide: {
		days: {
			date: string;
			overall_level: ForecastLevel;
			cells_by_level: Record<ForecastLevel, number>;
			most_at_risk: { cell: string; place: string | null; level: ForecastLevel; median_mm: number; chance_ge_40mm: number }[];
		}[];
	};
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS_FULL = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const DAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const LAGOS = 'Africa/Lagos';
const STALE_MS = 36 * 60 * 60 * 1000;

export function fmtOn(iso: string): string {
	return `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
}

/** IMERG 0.1° cells are centred on x.x5. */
export function cellIdAt(lon: number, lat: number): string {
	const snap = (v: number) => Math.round((v - 0.05) / 0.1) * 0.1 + 0.05;
	return `c${snap(lat).toFixed(2)}N${snap(lon).toFixed(2)}E`;
}

export function cellContaining(file: ForecastFile, lon: number, lat: number): ForecastCell | null {
	return file.cells[cellIdAt(lon, lat)] ?? null;
}

export function cellPolygon(lon: number, lat: number): [number, number][] {
	const h = 0.05;
	return [
		[lon - h, lat - h],
		[lon + h, lat - h],
		[lon + h, lat + h],
		[lon - h, lat + h],
	];
}

function weekdayIndex(isoDate: string): number {
	const [y, m, d] = isoDate.split('-').map(Number);
	return new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay();
}

export function weekdayFull(isoDate: string): string {
	return DAYS_FULL[weekdayIndex(isoDate)];
}

export function weekdayShort(isoDate: string): string {
	return DAYS_SHORT[weekdayIndex(isoDate)];
}

function pad2(n: number): string {
	return n < 10 ? `0${n}` : String(n);
}

function hourOf(stamp: string): number {
	return Number(stamp.slice(11, 13));
}

function partOfDay(hh: number): string {
	if (hh >= 5 && hh < 12) return 'morning';
	if (hh >= 12 && hh < 17) return 'afternoon';
	if (hh >= 17 && hh < 21) return 'evening';
	return 'night';
}

function windowOf(day: ForecastDay): { startH: number; endH: number } {
	if (day.risk.hours.length) {
		const r = day.risk.hours[0];
		return { startH: hourOf(r.start), endH: hourOf(r.end) };
	}
	const startH = Number(day.rain.peak_3h.start_hour_local.slice(0, 2));
	return { startH, endH: (startH + 3) % 24 };
}

export function windowLabel(day: ForecastDay): string {
	const { startH, endH } = windowOf(day);
	return `${pad2(startH)}:00–${pad2(endH)}:00`;
}

export function windowStartPhrase(day: ForecastDay): string {
	const { startH } = windowOf(day);
	return `${pad2(startH)}:00 on ${weekdayFull(day.date)}`;
}

function worstDay(days: ForecastDay[]): ForecastDay | null {
	if (!days.length) return null;
	return [...days].sort(
		(a, b) => LEVEL_RANK[b.level] - LEVEL_RANK[a.level] || b.rain.chance_ge_40mm - a.rain.chance_ge_40mm,
	)[0];
}

/** One-sentence Coming-up headline from the worst day in the next 7. */
export function comingUpHeadline(days: ForecastDay[]): string {
	const worst = worstDay(days);
	if (!worst || worst.level === 'none') return 'No heavy rain expected in the next 7 days.';
	if (worst.level === 'low') {
		return `Rain likely ${weekdayFull(worst.date)}, but no heavy rain expected in the next 7 days.`;
	}
	const verb = worst.level === 'high' ? 'likely' : 'possible';
	const { startH } = windowOf(worst);
	let line = `Heavy rain ${verb} ${weekdayFull(worst.date)} ${partOfDay(startH)} (${windowLabel(worst)})`;
	if (worst.risk.near_high_tide) line += ', close to high tide';
	return `${line}.`;
}

function lagosParts(now: Date): Record<string, string> {
	return Object.fromEntries(
		new Intl.DateTimeFormat('en-GB', {
			timeZone: LAGOS,
			weekday: 'long',
			day: 'numeric',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
			hourCycle: 'h23',
		})
			.formatToParts(now)
			.map((p) => [p.type, p.value]),
	);
}

export function forecastFreshness(generatedAt: string, now = Date.now()): { stale: boolean; madeLine: string } {
	const t = Date.parse(generatedAt);
	const parts = lagosParts(new Date(t));
	const stale = Number.isFinite(t) && now - t > STALE_MS;
	if (stale) {
		return { stale: true, madeLine: `This forecast is out of date (made ${parts.day} ${parts.month} ${parts.year})` };
	}
	return { stale: false, madeLine: `Forecast made ${parts.weekday}, ${parts.hour}:${parts.minute} (Lagos time)` };
}

export function pct40(chance: number): string {
	return `40 mm+: ${Math.round(chance * 100)}% chance`;
}

export function analoguesLine(nQualifying: number, nFlood: number): string {
	const days = nQualifying === 1 ? 'day' : 'days';
	return `Of ${nQualifying} past ${days} with similar rain here, ${nFlood} had floods reported within 5 km.`;
}

function joinAnd(names: string[]): string {
	if (names.length <= 1) return names[0] ?? '';
	if (names.length === 2) return `${names[0]} and ${names[1]}`;
	return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

export function whatToDo(level: ForecastLevel, windowStart: string | null, roads: string[]): string[] {
	if (level === 'none' || level === 'low') return ['No action needed. Check again before the weekend.'];
	const before = windowStart ?? 'the rain';
	const lines: string[] = [`Move valuables and documents off the floor before ${before}.`];
	if (roads.length) {
		lines.push(
			level === 'high'
				? `Avoid ${joinAnd(roads)} during the window.`
				: `Avoid ${joinAnd(roads)} if the rain is heavy.`,
		);
	}
	lines.push("Don't walk or drive through flood water: you can't see how deep it is or what is under it.");
	if (level === 'high') lines.push('Check on neighbours who may need help.');
	// No emergency numbers: none could be confirmed on an official Lagos State or LASEMA page (21 Oct 2026).
	return lines;
}

export interface ImpactsSummary {
	roads: { name: string; lengthUnderWaterM: number }[];
	facilities: { name: string; kind: string }[];
	buildings: number;
}

export function impactsLine(imp: ImpactsSummary): string | null {
	const bits: string[] = [];
	const roadNames = [...new Set(imp.roads.map((r) => r.name))].slice(0, 6);
	if (roadNames.length) bits.push(`Roads in spots reported flooded nearby: ${roadNames.join(', ')}.`);
	const schools = [...new Set(imp.facilities.filter((f) => f.kind === 'school').map((f) => f.name))];
	if (schools.length) bits.push(`Near a school: ${schools.slice(0, 3).join(', ')}.`);
	const hospitals = [...new Set(imp.facilities.filter((f) => f.kind === 'hospital' || f.kind === 'clinic').map((f) => f.name))];
	if (hospitals.length) bits.push(`Near a hospital or clinic: ${hospitals.slice(0, 3).join(', ')}.`);
	if (imp.buildings > 0) bits.push(`About ${imp.buildings.toLocaleString('en-GB')} mapped buildings sit inside those spots (their edges are rough).`);
	return bits.length ? bits.join(' ') : null;
}

export function mappedFloodId(isoDate: string, catalogIds: string[]): string | null {
	const id = `lagos-${isoDate}`;
	return catalogIds.includes(id) ? id : null;
}

export function citywideHeadline(
	file: Pick<ForecastFile, 'citywide' | 'meta'>,
	now = Date.now(),
): { quiet: boolean; text: string } {
	const days = file.citywide.days;
	const worst = [...days].sort((a, b) => LEVEL_RANK[b.overall_level] - LEVEL_RANK[a.overall_level])[0];
	const made = forecastFreshness(file.meta.run.generated_at, now);
	const madeShort = made.stale ? `forecast made ${fmtOn(file.meta.run.generated_at.slice(0, 10))}` : `forecast made ${made.madeLine.replace('Forecast made ', '').replace(' (Lagos time)', '')}`;
	if (!worst || worst.overall_level === 'none') {
		return { quiet: true, text: `No heavy rain expected in Lagos in the next 7 days (${madeShort}).` };
	}
	const places: string[] = [];
	for (const d of [...days].sort((a, b) => LEVEL_RANK[b.overall_level] - LEVEL_RANK[a.overall_level])) {
		if (LEVEL_RANK[d.overall_level] < LEVEL_RANK.medium) continue;
		for (const x of d.most_at_risk) {
			if (x.place && !places.includes(x.place)) places.push(x.place);
		}
	}
	const verb = worst.overall_level === 'high' ? 'likely' : worst.overall_level === 'medium' ? 'possible' : 'possible';
	const lead =
		worst.overall_level === 'low'
			? `Rain likely ${weekdayFull(worst.date)}`
			: `Heavy rain ${verb} ${weekdayFull(worst.date)}`;
	const area = places.length ? ` Areas most at risk: ${joinAnd(places.slice(0, 6))}.` : '';
	return { quiet: false, text: `${lead}.${area}` };
}

export function licenceFootnote(meta: ForecastFile['meta']): string {
	const licences = [...new Set(meta.sources.map((s) => s.licence).filter(Boolean))];
	const licenceBit = licences.length ? ` ${licences.join(' · ')}.` : '';
	return (
		"Rain forecast: ECMWF ensemble via Open-Meteo. Tides: EOT20. Reported floods undercount real floods, so 'no floods reported' is not proof it's safe." +
		licenceBit
	);
}

/** DEV-only fixture; production always reads latest.json even with ?forecast=fixture. */
export function forecastUrl(isDev: boolean, search: string): string {
	const q = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
	if (isDev && q.get('forecast') === 'fixture') return '/events/forecast/_fixture_storm.json';
	return '/events/forecast/latest.json';
}

let cached: Promise<ForecastFile | null> | null = null;

export function loadForecast(): Promise<ForecastFile | null> {
	return (cached ??= (async () => {
		const url = forecastUrl(import.meta.env.DEV, typeof location === 'undefined' ? '' : location.search);
		try {
			const res = await fetch(url);
			if (!res.ok) return null;
			return (await res.json()) as ForecastFile;
		} catch {
			return null;
		}
	})());
}

/** Test hook: drop the memo so a later load can see a new file. */
export function resetForecastCache(): void {
	cached = null;
}

/** Map an hourly median rain rate onto the same four levels the day badges use. */
export function hourlyBand(mm: number): ForecastLevel {
	if (mm >= 10) return 'high';
	if (mm >= 3) return 'medium';
	if (mm > 0.2) return 'low';
	return 'none';
}

export function levelFill(level: ForecastLevel, stale: boolean, alpha = 110): [number, number, number, number] {
	if (level === 'none') return [0, 0, 0, 0];
	const rgb = stale ? LEVEL_RGB.none : LEVEL_RGB[level];
	return [...rgb, alpha];
}
