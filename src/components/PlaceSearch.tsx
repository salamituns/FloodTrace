import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { KIND_LABEL, loadSearchIndex, searchPlaces, type SearchIndex, type SearchItem } from '../lib/area'
import { useStore } from '../state/store'
import '../styles/area.css'

export function PlaceSearch() {
	const listId = useId()
	const inputRef = useRef<HTMLInputElement>(null)
	const openArea = useStore((s) => s.openArea)
	const searchFocusNonce = useStore((s) => s.searchFocusNonce)
	const [index, setIndex] = useState<SearchIndex | null>(null)
	const [q, setQ] = useState('')
	const [open, setOpen] = useState(false)
	const [active, setActive] = useState(0)
	const [err, setErr] = useState<string | null>(null)

	useEffect(() => {
		if (searchFocusNonce) inputRef.current?.focus()
	}, [searchFocusNonce])

	useEffect(() => {
		loadSearchIndex()
			.then(setIndex)
			.catch((e: unknown) => setErr(String(e)))
	}, [])

	const results = index ? searchPlaces(q, index.items, 8) : []
	const show = open && q.trim().length >= 2

	const pick = (item: SearchItem) => {
		openArea({ lon: item.lon, lat: item.lat, label: item.name })
		setQ(item.name)
		setOpen(false)
		inputRef.current?.blur()
	}

	const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
		if (e.key === 'Escape') {
			setOpen(false)
			return
		}
		if (!show || !results.length) {
			if (e.key === 'ArrowDown' && results.length) setOpen(true)
			return
		}
		if (e.key === 'ArrowDown') {
			e.preventDefault()
			setActive((i) => Math.min(results.length - 1, i + 1))
		} else if (e.key === 'ArrowUp') {
			e.preventDefault()
			setActive((i) => Math.max(0, i - 1))
		} else if (e.key === 'Enter') {
			e.preventDefault()
			const hit = results[active] ?? results[0]
			if (hit) pick(hit)
		}
	}

	return (
		<div className="place-search">
			<label className="place-search__label" htmlFor="place-search-input">
				Search your street or area
			</label>
			<input
				id="place-search-input"
				ref={inputRef}
				className="place-search__input"
				type="search"
				role="combobox"
				placeholder="Search your street or area"
				autoComplete="off"
				spellCheck={false}
				aria-autocomplete="list"
				aria-expanded={show}
				aria-controls={listId}
				aria-activedescendant={show && results[active] ? `${listId}-${active}` : undefined}
				value={q}
				onChange={(e) => {
					setQ(e.target.value)
					setOpen(true)
					setActive(0)
				}}
				onFocus={() => setOpen(true)}
				onBlur={() => window.setTimeout(() => setOpen(false), 120)}
				onKeyDown={onKey}
			/>
			{show && (
				<ul id={listId} className="place-search__list" role="listbox">
					{!index && !err && <li className="place-search__empty">Loading streets…</li>}
					{err && <li className="place-search__empty">Could not load search.</li>}
					{index && results.length === 0 && (
						<li className="place-search__empty">No matching street or area</li>
					)}
					{results.map((item, i) => (
						<li key={`${item.kind}-${item.name}-${item.area}-${item.lon}`} role="presentation">
							<button
								id={`${listId}-${i}`}
								type="button"
								role="option"
								aria-selected={i === active}
								className={`place-search__opt${i === active ? ' is-active' : ''}`}
								onMouseDown={(e) => e.preventDefault()}
								onClick={() => pick(item)}
							>
								<span className="place-search__name">{item.name}</span>
								<span className="place-search__meta">
									{KIND_LABEL[item.kind] ?? item.kind}
									{item.area ? ` · ${item.area}` : ''}
								</span>
							</button>
						</li>
					))}
				</ul>
			)}
		</div>
	)
}
