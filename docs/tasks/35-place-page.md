# Task 35: the place page, answer first (UI/UX pass, part 3)

Read `docs/design/WORDS.md` first. Its principles and word table apply to every string you write. The audience is residents and journalists first.

Tasks 33 (front door, places list) and 34 (One flood view) have landed. Read their changes before you start, and reuse their styles and components where they fit (the priority badge, the ✓/✗ signs, the folding pattern, the map key).

## Why
A visitor opening a place wants three answers: **does it flood, why, and did anyone fix it?** The current page fails them in four ways:
- **The answers are buried.** It opens with a 20-line verdict, then the "Evidence chain". Floods are split across two cards ("Floods here" for mapped floods, "Flood history" for news days), and promises come last.
- **The timeline contradicts the page.** The bottom timeline's Floods row shows only mapped floods: Agungi shows 1 there but 5 flood days in Flood history.
- **The map doesn't zoom on a direct link.** Opening `/?r=1#site=agungi-collector` leaves it on the whole city; it may only fit when the place is clicked.
- **Labels overlap.** Place labels collide with each other and with basemap names ("System 156" over "Lekki Phase", "Sangotedo" twice).

## Files you own
- `src/components/SitePanel.tsx`: `SiteDetail`, `BeforeAfter`, `Sparkline`, and the selected-place branch of `SitePanel`.
- `src/components/SiteHistory.tsx`, `src/components/SiteTimeline.tsx`.
- `src/components/MapView.tsx`: the site layers, the camera fit, label collisions, and Places-mode entries in the map key.
- New: `src/styles/place.css`. Edit `src/styles.css` only to delete rules your changes made unused.
- Don't change data files, `watchList.ts` rules, or the One flood components.

## A. New page order
1. **Header.**
   - "← All places".
   - The place name.
   - The structure in plain words, e.g. "Road drain on Agungi–Ajiran Road, draining to the lagoon".
   - Location precision on hover, not as text.
2. **At a glance**, a new card. It shows the same three signs as the places list, computed with `buildWatchList` for this place (same as-of default), so the two can never disagree.
   - **Priority badge.**
   - **Floods often:** "5 flood days reported since 2014; last 28 Jun 2026".
   - **Drains blamed:** "Environment Commissioner: drains too small (2024)", plus the imagery wording from WORDS.md.
   - **Not fixed:** "Bigger collector promised Jun 2024: overdue, no work seen".
   - Each line links (scrolls) to its section below.
3. **Our reading** (the verdict).
   - An evidence-strength label ("Evidence: weak / moderate / strong").
   - The text clamped to 3 lines, with "Read more".
   - Reviewed date and reviewer in small print.
4. **Floods.** Merge "Floods here" into Flood history to make one card.
   - The year strip.
   - Then the flood-day rows, newest first.
   - A row whose day is a mapped flood gets **"Replay this flood →"** (the old "Open event"), which keeps the loading state.
   - A mapped flood with no catalog day still gets a row, labelled "mapped flood".
   - The "nearby, less certain" toggle stays.
   - Footer: "Searched news from 2014; earlier years not searched."
5. **Promises.** Moved up, because "was it fixed?" is the second question.
   - A status badge in WORDS.md wording.
   - What was promised, then who and when.
   - "Due: <date>" or "No date given: we allow 12 months".
   - The quote, linking to its source.
   - "Last checked: <date>, <finding in words>".
6. **Who blamed what** (the old Evidence chain). Remove the arrow-string hint.
   - Cause chip, who, date, the quote linked to its source, and the imagery-status badge in WORDS.md wording.
   - The status note in small print.
   - Keep `focusClaimId` scrolling and highlighting.
7. **What changed on the ground.**
   - The summary sentence.
   - **Then and now** (BeforeAfter): label the slider ends with their dates, and keep the close-up tabs.
   - The sparklines go in a folded "Measurements" section, with plain titles: "Green cover in the rainy season", "Building close by (within 10 m)". Data source names go on hover. Flood years stay shaded, with a one-line key.
- Empty states follow WORDS.md, e.g. "No promises on record for this place."

## B. Bottom timeline (`SiteTimeline`)
- **Floods row.**
  - Plot the strong catalog flood days (`catalog_floods`, strength name/near) plus mapped floods, so the count matches the Floods card.
  - Each dot gets a tooltip: date, news-outlet count, and "mapped flood" where it applies.
  - In the all-places view, plot every place's strong days.
  - Header: "N flood days reported across 13 places since 2014. Pick a place to see its promises and changes."
- **Row labels:** Floods · Promises · Satellite images · Building close by.
- **Timeline start.** Begin at 2014, matching the search, unless a place has a mapped flood earlier (2011). In that case keep 2011, and grey out 2011–2013 with the hover note "news not searched".

## C. Map
- **Camera.** Fit the selected place on load, from a direct `#site=` link, as well as on click. Wait for the map and the sites to be ready.
- **Labels.**
  - No place label overlaps another place label at the default city view. Use deck.gl's `CollisionFilterExtension`, or show labels only for the selected or hovered place plus the top-priority ones. Pick one and say why.
  - Hide or drop basemap place-name labels that collide with place markers, if the style allows it. If not, place labels must have a white halo and win the collision.
- **Marker colour.** Colour place markers by priority, from the same tiers as the list, and add those entries to the map key in Places mode.

## Check
- `npx tsc --noEmit`, `npm run build` and `npx tsx scripts/check-watchlist.ts` all pass.
- For Agungi, Alpha Beach, Agric bridge (0 mapped floods) and Marina, report:
  - the At-a-glance lines;
  - the Floods card's row count;
  - the bottom timeline's dot count. The two counts must match.
- Report:
  - every string you changed, old → new;
  - any word you needed that WORDS.md lacks.
- No browser tools. I'll check the UI myself.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.

## Addendum: one way to count floods
The places list (via `buildWatchList`) counts strong **rain** (pluvial) flood days. The catalog also has river and sea floods. Olopo Meji, for example, shows 6 in the list and 7 in its catalog summary.
- **At a glance:** "6 flood days from rain reported…". The list wording stays.
- **The Floods card:** list every strong day, and tag each non-rain day "river" or "sea".
- **The card header:** give both numbers when they differ, e.g. "7 flood days reported (6 from rain)".
- **Bottom timeline:** match the card, plotting every strong day and drawing non-rain days hollow.
