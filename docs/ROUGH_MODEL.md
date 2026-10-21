# The rough model, and why it was dropped

For a while the 3D view had a second water layer, the "rough model": terrain
plus a rain scenario ("if 40 mm more rain falls than the drains can take"),
showing low ground where water could collect. It was clearly labelled as a
model, not a measurement, and it stayed off by default.

On 21 Oct 2026 we dropped it, because our own test found it matched reported
floods **no better than chance**. Placing the 178 reported flood spots at
random over the built-up area would have put about as many inside the model's
water as the model itself did, and the same was true of the radar flood map of
3 Jul 2024. A layer that adds no information should not be on the map, however
honest its label. The 3D view now shows reported floods only.

## The test

Each reported flood spot counts as a "hit" when its own 30 m cell is model-wet.
The random baseline is the share of built-up cells that are model-wet for that
scenario: scattering the spots at random would hit at that rate.
`events/rough_model/meta.json` is the full record.

| Scenario (excess rain) | Spots in the model's water | Hit rate | Random baseline |
|---|---|---|---|
| 20 mm | 4 of 178 | 2.2% | 4.1% |
| 40 mm | 4 of 178 | 2.2% | 4.6% |
| 60 mm | 4 of 178 | 2.2% | 4.8% |
| 80 mm | 4 of 178 | 2.2% | 4.8% |
| 100 mm | 80 of 178 | 44.9% | 43.8% |
| 150 mm | 85 of 178 | 47.8% | 45.3% |

Of the 57 built-up cells the radar saw flooded on 3 Jul 2024, the model had wet
0 at 20–80 mm, 27 at 100 mm and 38 at 150 mm.

The jump at 100 mm is not skill: nearly all low ground near the lagoon turns
wet at once, so the model "hits" almost everything in the flood-prone half of
the city, and the random baseline jumps with it. Terrain alone — height above
the nearest water, hollows and catchment area — does not pick out which street
floods. Our earlier terrain check
(`events/terrain/verdict.txt`) said the same: flooded spots sit about 2 cm
lower than their surroundings, while the DEM's vertical error is about 2 m.

## What is kept

- `pipeline/rough_model.py` — kept so the result can be reproduced. It also
  regenerates `roads.json` and `building_counts.json`, which the evidence
  impacts still use.
- `events/rough_model/meta.json` — the record of the negative result.
- `events/rough_model/roads.json`, `events/rough_model/building_counts.json` —
  still loaded by the "what's hit" layer, which now tests against evidence
  water only.

The scenario PNGs and `water_polygons.json` were deleted with the layer.
