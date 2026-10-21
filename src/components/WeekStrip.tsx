import {
	LEVEL_WORD,
	pct40,
	weekdayShort,
	type ForecastDay,
	type ForecastLevel,
} from '../lib/forecast';
import '../styles/forecast.css';
import '../styles/places.css';

export interface WeekStripDay {
	date: string;
	level: ForecastLevel;
	chance_ge_40mm: number;
}

export function weekDaysFrom(days: ForecastDay[]): WeekStripDay[] {
	return days.map((d) => ({ date: d.date, level: d.level, chance_ge_40mm: d.rain.chance_ge_40mm }));
}

export function LevelBadge({ level, stale }: { level: ForecastLevel; stale?: boolean }) {
	const word = LEVEL_WORD[level];
	const cls = stale || level === 'none' ? 'lowest' : word.toLowerCase();
	return (
		<span className={`places__prio places__prio--${cls}`}>
			<span className="places__prio-shape" aria-hidden="true" />
			{word}
		</span>
	);
}

export function WeekStrip({
	days,
	selected,
	stale,
	onSelect,
	onClear,
}: {
	days: WeekStripDay[];
	selected: string | null;
	stale: boolean;
	onSelect: (date: string) => void;
	onClear?: () => void;
}) {
	return (
		<>
			<div className="week-strip" role="list">
				{days.map((d) => (
					<button
						key={d.date}
						type="button"
						role="listitem"
						className={`week-strip__day${selected === d.date ? ' is-on' : ''}${stale ? ' is-stale' : ''}`}
						aria-pressed={selected === d.date}
						onClick={() => onSelect(d.date)}
					>
						<span className="week-strip__name">{weekdayShort(d.date)}</span>
						<LevelBadge level={d.level} stale={stale} />
						<span className="week-strip__chance">{pct40(d.chance_ge_40mm)}</span>
					</button>
				))}
			</div>
			{selected && onClear && (
				<button type="button" className="week-strip__clear" onClick={onClear}>
					Clear
				</button>
			)}
		</>
	);
}
