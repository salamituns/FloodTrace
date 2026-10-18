# Task 24b: terrain check with fairer controls

Context: Task 24 (`docs/tasks/24-terrain-check.md`, `pipeline/terrain_check.py`, `events/terrain_check.json`). The reviewer did
not accept the "pass" verdict, for three reasons.

1. **Elevation is confounded by geography.** Controls are drawn anywhere in the AOI and matched only on built-up level.
   - The AOI reaches Ogun State and the Epe/Badagry hinterland.
   - The 17 m `elev_min` gap (5.9 m vs 23.2 m) mostly says flood reports come from the low coastal city. It does not say
     they sit in local lows.
   - So `elev_min` is no longer a primary metric. Report it as descriptive only.
2. **The local signals are small next to DEM noise.**
   - HAND differs by −0.26 m, and depression share by +0.025.
   - The p-values (0.024, 0.015) haven't been corrected for 5 primary metrics.
3. **FABDEM is missing.**

## Do (extend `pipeline/terrain_check.py`; keep the Task 24 outputs for comparison)

### A. Two new control designs, run alongside the existing one

- **`matched_water`**: same as now, plus distance to lagoon/sea within ±25% of the point's (minimum ±500 m).
- **`local`**: 20 random land points in an annulus 1–3 km around each point.
  - Built-up 2020 within ±0.10 (widen to ±0.15 only if fewer than 10 are found, and record it).
  - Not within 1 km of any evidence point; the 1 km minimum is the existing rule, so keep it.
  - This design asks the question the app needs: *within its own neighbourhood, is the flooded spot lower or wetter?*

### B. Statistics

- Primary metrics are now the four local ones: `hand_min`, `dep_share_050`, `acc_log10_max` and `tpi_min`.
- Apply a **Holm correction** across these four, per design × subset, and report both raw and Holm p-values.
- Next to each median difference, also report it in units of DEM vertical error (2 m), so a reader can see whether the
  effect is above noise.

### C. FABDEM

- Retry data.bris, using the same URL.
- If it is still refused, try the mirror on Source Cooperative or a Hugging Face mirror.
  - Only use a mirror whose README names FABDEM V1-2 and the Bristol authors.
  - Record the URL, and check that its tile hashes or values match a FABDEM description where possible.
- If FABDEM is still unavailable, say so and continue on GLO-30.

### D. Verdict rule (fixed before looking at results)

- **pass**: in the `local` design, at least 2 of the 4 metrics are significant after Holm (p < 0.05) in the predicted
  direction, for the all-points subset. At least one of them must also be significant in the >2 km subset.
- **fail**: none are significant in the `local` design.
- **mixed**: anything else.
- Write the verdict for every design, but the `local` design decides.

## Outputs

- Update `events/terrain_check.json`: add `results.<dem>.<design>.<subset>.<metric>`, keeping the old run as design
  `builtup_only`. Add the verdict rule to `meta`.
- Add `percentile_local` to `events/drainage_sites_terrain.json`.
- Regenerate the box plots, one panel per design.
- Rewrite `events/terrain/verdict.txt`.
- Print the summary table: design × subset × metric, with diff, diff/2 m, p and Holm p.

## Rules

Same rules as Task 24:
- caches under `pipeline/cache/dem/`;
- delete intermediate files with `find … -type f -delete`; no `rm -rf`;
- run in the foreground;
- don't touch `src/`, `events/sites.json` or event folders;
- no commit.
