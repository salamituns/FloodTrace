import { useEffect, useMemo, useState } from 'react'
import {
	AREA_RADIUS_M,
	fmtDistance,
	fmtOn,
	haversineM,
	loadAreaRain,
	loadFloodSpots,
	NEARBY_PLACES_M,
	nearestRainCell,
	spotsWithin,
	type AreaRainFile,
	type FloodSpotsFile,
} from '../lib/area'
import { buildWatchList } from '../lib/watchList'
import { sitePoint } from '../sites/geo'
import { useStore } from '../state/store'
import { EMPTY_RAIN_SUMMARY, PRIORITY } from './SitePanel'
import { ForecastCard } from './ForecastCard'
import { ShowMeIn3DButton } from './Map3DShowMe'
import '../styles/area.css'
import '../styles/place.css'
import '../styles/places.css'

export function AreaPanel() {
	const sel = useStore((s) => s.selectedArea)!
	const closeArea = useStore((s) => s.closeArea)
	const openSite = useStore((s) => s.openSite)
	const loaded = useStore((s) => s.sites)
	const [spotsFile, setSpotsFile] = useState<FloodSpotsFile | null>(null)
	const [rain, setRain] = useState<AreaRainFile | null>(null)

	useEffect(() => {
		loadFloodSpots().then(setSpotsFile).catch(() => setSpotsFile(null))
		loadAreaRain().then(setRain).catch(() => setRain(null))
	}, [])

	const nearbySpots = useMemo(
		() => (spotsFile ? spotsWithin(spotsFile.spots, sel.lon, sel.lat, AREA_RADIUS_M) : []),
		[spotsFile, sel.lon, sel.lat],
	)
	const floodDays = useMemo(() => new Set(nearbySpots.flatMap((x) => x.spot.dates)).size, [nearbySpots])
	const lastDate = useMemo(() => {
		const dates = nearbySpots.flatMap((x) => x.spot.dates).sort()
		return dates[dates.length - 1] ?? null
	}, [nearbySpots])

	const nearbyPlaces = useMemo(() => {
		if (!loaded) return []
		const ranked = buildWatchList(loaded.sites, loaded.promises, EMPTY_RAIN_SUMMARY, new Date())
		const byId = new Map(ranked.map((r) => [r.site_id, r]))
		return loaded.sites
			.map((site) => {
				const [lon, lat] = sitePoint(site)
				return { site, m: haversineM(sel.lon, sel.lat, lon, lat), row: byId.get(site.site_id) }
			})
			.filter((x) => x.m <= NEARBY_PLACES_M && x.row)
			.sort((a, b) => a.m - b.m)
	}, [loaded, sel.lon, sel.lat])

	const rainLine = useMemo(() => {
		if (!rain) return null
		const cell = nearestRainCell(rain.cells, sel.lon, sel.lat)
		if (!cell) return null
		const n = cell.per_year >= 10 ? Math.round(cell.per_year) : Math.round(cell.per_year * 10) / 10
		return `Heavy rain (40 mm or more in a day) hits this area about ${n} times a year.`
	}, [rain, sel.lon, sel.lat])

	return (
		<aside className="right right--area" id="area-panel">
			<header className="place-head">
				<button className="back" type="button" onClick={closeArea}>
					← Back
				</button>
				<h2 className="site__name">{sel.label}</h2>
				<p className="site__structure">within 1.5 km</p>
			</header>

			<ForecastCard lon={sel.lon} lat={sel.lat} />

			<section className="card">
				<h3>Has it flooded here?</h3>
				<ShowMeIn3DButton lon={sel.lon} lat={sel.lat} />
				{spotsFile && nearbySpots.length > 0 && lastDate && (
					<p className="area-answer">
						Yes: {floodDays} flood day{floodDays === 1 ? '' : 's'} reported nearby since 2014; last {fmtOn(lastDate)}.
					</p>
				)}
				{spotsFile && nearbySpots.length === 0 && (
					<p className="area-answer">
						No floods reported within 1.5 km since 2014. That isn't proof it's safe: news covers some areas far more than
						others.
					</p>
				)}
				{!spotsFile && <p className="empty">Loading flood spots…</p>}
				{nearbySpots.length > 0 && (
					<ul className="area-spots">
						{nearbySpots.map(({ spot, m }) => (
							<li key={`${spot.name}-${spot.lon}-${spot.lat}`}>
								<b>{spot.name}</b>
								<small>
									{fmtDistance(m)} · {spot.count} flood day{spot.count === 1 ? '' : 's'} · last {fmtOn(spot.latest)}
								</small>
								<span className="area-dates">{spot.dates.map(fmtOn).join(', ')}</span>
								{spot.depths
									.filter((d) => d.placed_by === 'same_sentence' || d.placed_by === 'single_area')
									.map((d) => (
										<q key={d.phrase}>
											{d.url ? (
												<a href={d.url} target="_blank" rel="noreferrer">
													{d.phrase}
												</a>
											) : (
												d.phrase
											)}
										</q>
									))}
								{spot.reports.length > 0 && (
									<span className="area-reports">
										{spot.reports.map((r) => (
											<a key={r.url} href={r.url} target="_blank" rel="noreferrer">
												{r.publisher}
											</a>
										))}
									</span>
								)}
							</li>
						))}
					</ul>
				)}
			</section>

			<section className="card">
				<h3>Places we track nearby</h3>
				{nearbyPlaces.length === 0 ? (
					<p className="empty">None of the places we track sit within 3 km.</p>
				) : (
					<ul className="area-places">
						{nearbyPlaces.map(({ site, m, row }) => {
							const prio = PRIORITY[row!.tier] ?? 'Lowest'
							return (
								<li key={site.site_id}>
									<button type="button" className="area-place" onClick={() => openSite(site.site_id)}>
										<span>
											<b>{site.name}</b>
											<small>
												{fmtDistance(m)} · {site.structure_name}
											</small>
										</span>
										<span className={`places__prio places__prio--${prio.toLowerCase()}`}>
											<span className="places__prio-shape" aria-hidden="true" />
											{prio}
										</span>
									</button>
								</li>
							)
						})}
					</ul>
				)}
			</section>

			<section className="card">
				<h3>Rain here</h3>
				<p className="area-answer" title="NASA GPM IMERG, ~10 km cells">
					{rainLine ?? 'Loading rain history…'}
				</p>
			</section>
		</aside>
	)
}
