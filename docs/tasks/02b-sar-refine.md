# Task 02b — refine the SAR classes (follow-up to Task 02)

Review of Task 02 output (thanks for flagging the urban class honestly):
- Class 4 (+3 dB brightening on bright pixels) is spread evenly over the whole mainland — that's the signature of
  **wet soil / wet surfaces after rain**, not street flooding. It must not be presented as flooding.
- The during-flood VV image shows **bright blotches on Lagos Lagoon**: rain cells roughening the water surface.
  That is valuable evidence of *where heavy rain was falling at 06:30 WAT* and should become its own class.
- The left (west) part of the AOI has no data in the during scene (swath edge).

Change `pipeline/sar_flood.py` (keep everything else as is; thresholds stay named constants recorded in stats.json):

1. Rename class 4 → `surface_wetting` ("backscatter increase on land — wet soil or surfaces; may include urban flooding;
   not flood evidence on its own"), confidence `low`. Keep it in `classes.tif`, but **exclude it from `flood.geojson`**;
   write it to a separate `wetting.geojson` instead.
2. New class 5 `rain_cell_on_water` — pixels that are `permanent_water` (pre and post < −16 dB) where
   during VV − pre VV > +4 dB. Smooth with a 9×9 majority/median before polygonising. Write `rain_cells.geojson`
   (dissolved, drop < 5 ha), property `class`, `confidence: "moderate"`, `area_ha`, plus `observed_at` = the during-scene
   acquisition time (ISO, WAT). Add area to stats.json.
3. New class 255 `no_data` where the during scene has no coverage; record covered fraction of the AOI in stats.json.
4. Update `preview_classes.png` colours/legend accordingly (rain cells in a distinct colour, e.g. cyan; wetting faint).
5. Re-run for `events/lagos-2024-07-03` and print the new summary (areas per class, coverage fraction, outputs).

Don't touch `src/`. Don't commit.
