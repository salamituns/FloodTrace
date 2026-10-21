# Task 39b: fix depth attribution in flood spots

Review of Task 39. Search works well. One faithfulness bug blocks the 3D work.

## The bug
`build_flood_spots.py` attaches a report's depth phrase to **every** area that the report lists.

Example: `guardian.ng/news/how-lagos-downpour-wreaked-havoc-gridlock/` lists 21 areas. Its text says "at Agric, Ikorodu, water on the road to Asolo in Isawo was **knee-high**". Yet "knee-high" now sits on Agege, Oshodi, Lagos Island, Surulere, Ajegunle and the rest.

Likewise, "up to six feet high over the roads" is attached to Lekki from a report listing Ikoyi, Lekki Peninsula and Victoria Island, although the sentence doesn't say where the water was that deep.

Task 40 will draw these as water at that depth in 3D, so as things stand we would show water depths no source reported.

## The fix
Attach a depth phrase to a spot only when **one** of these holds:
1. **Same sentence.** The phrase and the spot's area name (or one of its alt spellings, or the report's area string for it) appear in the same sentence of `impacts` or `quote`. Use case-insensitive, punctuation-tolerant matching, so "Agric, Ikorodu" matches the area "Agric, Ikorodu".
2. **Single area.** The report lists exactly one area, so the depth can only be about that area.

Otherwise, don't attach it to any spot. Keep it in a report-level list in `meta`, named something like `depth_unplaced`, holding the phrase, url and the reason it wasn't placed. That keeps it visible to us without putting it on the map.

For each placed depth, add `"placed_by": "same_sentence" | "single_area"` and the sentence itself (`"sentence"`, word for word).

## Check
- Rerun, and report the new `n_with_depth` and every placed depth: spot → phrase → placed_by → sentence.
- The Guardian "wreaked havoc" knee-high must land only on the Agric, Ikorodu spot, or be unplaced if that spot didn't geocode. Say which.
- `npx tsc --noEmit` and `npm run build` still pass. If the field change touches `AreaPanel.tsx`, update it so it shows only placed depths.

## Rules
- Foreground only.
- No `rm -rf`.
- Don't commit.
- Don't start a dev server or open a browser.
- Droid is working on Task 40 in `MapView.tsx`, `LayersPanel.tsx`, `store.ts` and the new rough-model files. Don't touch those.
