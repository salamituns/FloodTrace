/**
 * Unit checks for area-panel news links and search collapse (Task 43).
 *
 *   npx tsx scripts/check-area.ts
 */
import {
	collapseNearbySearchHits,
	fmtOn,
	newsLinkText,
	uniqueNewsLinks,
	type SearchItem,
} from '../src/lib/area'

let failed = 0
function check(ok: boolean, msg: string): void {
	if (!ok) {
		failed += 1
		console.error(`FAIL  ${msg}`)
	} else {
		console.log(`ok    ${msg}`)
	}
}

const punchJul = {
	url: 'https://punchng.com/heavy-rain-floods-lagos-roads-agencies-warn-of-more-risks/',
	publisher: 'Punch',
	date: '2026-07-13',
}
const punchDup = { ...punchJul, publisher: 'Punch Newspapers' }
const premium = {
	url: 'https://www.premiumtimesng.com/regional/ssouth-west/891405-heavy-rainfall-floods-lagos-communities-disrupts-airport-operations.html',
	publisher: 'Premium Times',
	date: '2026-06-28',
}

const links = uniqueNewsLinks([punchJul, premium, punchDup])
check(links.length === 2, `dedupe by url: ${links.length}`)
check(links[0].url === punchJul.url, 'newest first')
check(
	newsLinkText(punchJul) === 'Punch, 13 Jul 2026',
	`label: ${newsLinkText(punchJul)}`,
)
check(fmtOn('2026-07-13') === '13 Jul 2026', 'date words')

const a: SearchItem = {
	name: 'Ojuelegba Road',
	kind: 'bridge',
	area: 'Ojuelegba',
	lon: 3.3645,
	lat: 6.5099,
}
const b: SearchItem = {
	name: 'Ojuelegba Road',
	kind: 'bridge',
	area: 'Yaba',
	lon: 3.3647,
	lat: 6.51,
	alt: ['Ojuelegba Rd'],
}
const collapsed = collapseNearbySearchHits([a, b])
check(collapsed.length === 1, `collapse nearby same name+kind: ${collapsed.length}`)
check(collapsed[0].area === 'Yaba', 'keep the entry with more detail')

if (failed) {
	console.error(`\n${failed} failed`)
	process.exit(1)
}
console.log('\nall ok')
