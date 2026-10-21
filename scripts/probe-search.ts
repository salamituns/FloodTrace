/**
 * Throwaway probe for Task 39: top 3 index hits for the listed queries.
 *   npx tsx scripts/probe-search.ts
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { searchPlaces, type SearchIndex } from '../src/lib/area'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const index = JSON.parse(readFileSync(path.join(root, 'events/search_index.json'), 'utf8')) as SearchIndex
const queries = ['Agungi', 'allen avenue', 'lekki phase 1', 'ojuelegba', 'Yaba bus stop', 'ikorodu road']

let failed = 0
for (const q of queries) {
  const hits = searchPlaces(q, index.items, 8)
  console.log(`\n${JSON.stringify(q)}`)
  if (!hits.length) {
    console.log('  (no hits)')
    continue
  }
  hits.slice(0, 3).forEach((h, i) => {
    console.log(`  ${i + 1}. ${h.name} [${h.kind}] ${h.area ?? '—'}  ${h.lon.toFixed(4)},${h.lat.toFixed(4)}`)
  })
  if (q === 'ojuelegba') {
    const keys = hits.map((h) => `${h.kind}|${h.name.toLowerCase()}`)
    const dup = [...new Set(keys.filter((k, i) => keys.indexOf(k) !== i))]
    if (dup.length) {
      failed += 1
      console.error(`  duplicates: ${dup.join(', ')}`)
    }
  }
}

if (failed) {
  console.error('\nojuelegba still has duplicate name+kind hits')
  process.exit(1)
}
