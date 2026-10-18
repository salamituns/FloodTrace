# Task 23 — `pipeline/build_sites.py`: merge everything into `events/sites.json`

Context: `docs/SITES_PLAN.md` (read it first: the `events/sites.json` schema is the spec). Cursor is writing
`events/promises.json` in parallel (Task 22). Build the script so it runs with or without that file, and re-run it when the
file appears.

## Inputs
`events/drainage_sites.json`, `events/drainage_sites_imagery.json`, `events/drainage_sites_s2.json`,
`events/drainage_sites_buildings.json`, `events/*/evidence.geojson` (+ `meta.citywide_cause_statements`), `events/catalog.json`,
optional `events/promises.json`, and the previous `events/sites.json` (for reviewer fields).

## Rules
1. **Sites:** one per `drainage_sites.json` entry. `name` = a short human name (e.g. "Alpha Beach – System 156"). `aliases` from
   the evidence `location_name`s matched below. `structure_type` from `structure_name`.
2. **Floods:** for **every** event, evidence features within `radius_m` (default 400 m; use 600 m for LineStrings longer than
   2 km) of the site geometry, excluding `location_confidence: "lga"`. Record ids, count and nearest distance. Include events
   other than the site's own (that's the point: recurring places).
3. **Claims:** evidence features in the site's `evidence_ids` plus any matched feature with human `causes`, as in the schema.
   `evidence_status`: take it from the "Cause (preliminary)" section of that event's `dossier.md` where the site is listed
   (map `imagery supports`→supports, `imagery inconclusive`→inconclusive, `not checked`→not_checked,
   `no imagery after event`→no_imagery_after). If it's not listed, use `not_checked`.
4. **Change:**
   - `wayback`: the imagery list (acq_date, file, marked_file; detail chips too).
   - `s2_wet_season.by_year`: the **May–Oct median** vegetated fraction per year per AOI, computed from the monthly series.
     Don't use the step detector's output. For alpha-beach-156 use the `__south` AOI and record which AOI.
   - `buildings_0_10m`: by-year built fraction, plus `matched_pct` and `matched_n` computed my way: rank the site's 2016→2023
     change against baseline segments whose 2016 20–50 m built fraction is within ±max(0.05, 0.5 × the site's). Mark
     `ikorodu-dammed` and `ijede-drain` `excluded: "corridor is not a channel"`.
5. **Promises:** `promise_ids` from `promises.json` where present.
6. **Reviewer fields** (`verdict`, `change.summary`): copy from the previous `sites.json` by site_id. If any input number feeding
   that site changed since, set `stale: true`. On first run, leave them `null`.
7. Validate against the schema (write a small JSON Schema in `pipeline/schemas/sites.schema.json` and check with `jsonschema`).
   Print a table: site, n floods (events), n claims, statuses, S2 years, OB matched pct, n promises.

Deterministic output (sorted keys and lists), and re-runnable. Don't touch `src/` or other files. No background processes.
Don't commit.
