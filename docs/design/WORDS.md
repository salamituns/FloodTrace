# FloodTrace: design principles and words

Written for the UI/UX pass (Tasks 33–36).
- **Audience:** residents, journalists and advocates first. Officials can still use it.
- **Rule:** every task in this pass follows this page. If a word you need isn't here, choose the plainest one and list it in your report.

## Principles
1. **Answer first, evidence one click away.** Each screen opens with the answer to its question in one sentence. Sources, quotes and method sit underneath, folded or on hover. Never hide them, because evidence is the product.
2. **One question per screen.**
   - **Places that flood:** "Which places keep flooding, and was anything fixed?"
   - **A place:** "Does it flood, why, and did anyone fix it?"
   - **One flood:** "What happened during this flood, hour by hour?"
3. **No dead ends.** If a control does nothing, remove it. Never show "arrives in a later phase".
4. **Calm by default.** Show the fewest layers, charts and cards that answer the screen's question. Everything else can be switched on.
5. **Plain words on screen; technical names on hover.** Data sources such as IMERG, Sentinel-1, EOT20, GHSL and OSM belong in a hover note or a "Sources" line, not in titles or labels.
6. **Honest about gaps.** Keep the caveats (e.g. "a place with no reports can still flood"), but say them once, briefly, where they matter.
7. **Every colour means one thing everywhere.**
   - Red: flood reported.
   - Amber: promise not kept.
   - Green: delivered / fixed.
   - Blue: water and rain.
   - Grey: unknown or not checked.

## Words

| Internal / current | On screen | Hover note (when useful) |
|---|---|---|
| Incident mode | **One flood** | Replays a single flood hour by hour: rain, tide, radar and reports. |
| Sites mode | **Places that flood** | The places that keep flooding across every flood on record. |
| site | **place** | A drain, canal or road stretch that floods repeatedly. |
| event (Tier A) | **flood** (in lists: "mapped flood") | A flood we mapped in detail, report by report. |
| strong flood day (`name`/`near`) | **flood day reported** | A day the news named this place, or a spot within about 1 km, as flooded. |
| area match (less certain) | **nearby, less certain** | Reports named the wider area, not this place. |
| outlets | **news outlets** | |
| claim | **what was blamed** / "who blamed what" | |
| cause chip | (cause label as is: Blocked drains, Inadequate drains …) | |
| evidence_status `supports` | **Imagery agrees** | |
| `weak` | **Imagery partly agrees** | |
| `inconclusive` | **Imagery can't tell** | |
| `contradicts` | **Imagery disagrees** | |
| `not_checked` | **Not checked yet** | |
| `no_imagery_after` | **No imagery after the flood** | |
| Evidence chain | **Who blamed what** | Each claim, who made it, and what satellite images show. |
| verdict | **Our reading** | FloodTrace's summary of the evidence, with date reviewed. |
| promise status `overdue` | **Overdue** | Promised, past its date, nothing visible in imagery. |
| `no_visible_work` | **No work seen** | |
| `stalled` | **Stalled** | |
| `in_progress` | **Work under way** | |
| `unverifiable` | **Can't check from imagery** | E.g. desilting or removals that satellites can't see. |
| `delivered` | **Done** | |
| Pre-season watch list | **Places that flood** (ranked list) | Ranked as of today by default; pick 1 March to see the pre-season list. |
| Tier 3 / 2 / 1 / 0 | **High / Medium / Low / Lowest** priority | Number of warning signs present (out of 3). |
| test "Repeated flooding" | **Floods often** | ≥ 2 flood days reported, one in the last 3 rainy seasons. |
| test "Named drainage failure" | **Drains blamed** | An official or reporter blamed the drains, or imagery agrees. |
| test "No visible fix" | **Not fixed** | No promised fix is visibly done. |
| as of | **as of** (date) | The list as it would have looked on this date. |
| Built ≤10 m (Open Buildings, per place) | **Building close by** | Share of land within 10 m of the channel that's built on (Open Buildings). |
| Built over since 2000 (GHSL map layer) | **Land built over since 2000** | GHSL built-up surface, 2000 → latest. |
| What changed | **What changed on the ground** | |
| Before/after imagery | **Then and now** | |
| Rainfall rate (IMERG) | **Rain** | NASA GPM IMERG, 30-min, ~10 km cells. |
| Radar flood extent (S1) | **Water seen by radar** | Sentinel-1 radar pass; open water only, misses water under buildings. |
| Radar rain cells (S1) | **Storm cells seen by radar** | |
| Drainage & canals (OSM) | **Drains and canals** | OpenStreetMap. |
| Media evidence | **News reports** | |
| Analysis points | **Chart points** | The spots the rain and tide charts read from. Not real gauges. |
| Tide (offshore) EOT20 | **Tide** | Modelled offshore tide (EOT20); no public lagoon gauge. |
| rain–tide conflict / tidal lock | **High tide during heavy rain** | When the tide is high, drains to the lagoon empty more slowly. |
| Focus window | **Main hours** | |
| Cause (prelim.) | **Likely cause** | |
| Open questions | **Still unknown** | |
| ids such as `lagos-2024-07-03` | never on screen | |

## Layout conventions
- **Card title:** a sentence-case noun phrase. Put a one-line answer under it, in the body text colour, before any detail.
- **Counts:** "5 flood days reported since 2014", not "5 strong days in 13 years searched".
- **Dates:** "3 Jul 2024" in prose, ISO dates only in hover notes.
- **Empty states:** say what's missing and why. For example: "No promises on record for this place."
