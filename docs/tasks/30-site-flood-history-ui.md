# Task 30: "Flood history" on the site pages

Context:
- `docs/tasks/29-site-flood-counts.md`: what `catalog_floods[]` and `catalog_summary` mean.
- `events/sites.json`: each site now has both fields. `meta.search_coverage` in `events/flood_days.json` is where
  `years_searched` comes from. The sweep covers 2014–2026 and is closed.
- `src/components/SitePanel.tsx`: the site detail. The "Floods here" card lists only Tier A events (`site.floods`).

Goal: a reader opening a site sees how often it has flooded in the news record, each day with its sources, and how far
to trust the count.

## Do
1. **Types:** in `src/sites/types.ts`, add `CatalogFlood` and `CatalogSummary` matching the JSON (strength
   `'name' | 'near' | 'area'`; flood_type `'pluvial' | 'riverine' | 'lagoon' | 'coastal'`). Both are optional on
   `SiteRecord`, so an older sites.json still loads.
2. **New card "Flood history"**, directly after "Floods here", in its own component file `src/components/SiteHistory.tsx`:
   - **Header hint:** "`n_days_strong` strong days in `years_searched.length` years searched".
   - **Year strip:** one cell per searched year, oldest to newest. A cell is filled when a strong day falls in that
     year and outlined when only `area` matches do. Hovering a cell (title attribute is enough) gives the dates.
   - **List**, newest first, strong days only (`name` and `near`):
     - date; a type chip when not pluvial; "N outlets"; a "deaths" marker is out of scope, skip it;
     - the matched area names and how they matched: "named" for `name`, "within N m" for `near`;
     - the first source as a link (publisher name) with its quote in small text; "+N more" reveals the rest;
     - "Open event →" when `tier_a_event_id` is set, reusing the existing `openEvent` handler.
   - **`area` matches** go behind a collapsed "N nearby, less certain" toggle, each with its distance.
   - **Footer note,** in small text: `catalog_summary.note`, plus "Searched 2014–2026; earlier years not searched."
     Build the range from `years_searched`, don't hard-code it.
   - Don't show `per_searched_year` as a headline number. The early years are thin, so the rate is only useful for
     comparing sites.
3. **Site list:** the "Floods here" count in `SiteList` stays. Add the strong-day count as a second small figure, and
   sort by it, then by Tier A events, then by name.
4. **Styles:** reuse the existing card, chip, `site-floods` and `link` classes in `src/styles.css`. Add only what the year
   strip needs, using the existing colour variables. Keep light and dark themes working.

## Check
- `npx tsc --noEmit` and `npm run build` pass.
- In the running dev server (port 5317, already running, don't start another), open these and screenshot the card:
  - agungi-collector: 5 strong days, 2026-06-28 at the top, named "Agungi";
  - olopomeji: 7 strong days;
  - ikorodu-dammed: 0 strong days. The card says so plainly ("No reported floods matched in 13 years searched") and
    doesn't vanish.
- Report the list order of the site list.

## Rules
- Don't touch `pipeline/`, `events/` or the docs other than this file.
- Foreground only. No `rm -rf`. Don't commit.
