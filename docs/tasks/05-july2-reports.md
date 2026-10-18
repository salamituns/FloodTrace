# Task 05 — was there flooding on 2 July 2024?

IMERG shows a short, intense burst over **Lekki and Lagos Island on Tue 2 July 2024, ~11:00–15:30 WAT (~22 mm/h peak in a
10 km cell)** — heavier than anything on 3 July — but no report collected so far mentions 2 July. Find out whether it flooded.

1. Search news / official / social coverage dated **2 July 2024** (and 3 July articles that describe "yesterday" / "Tuesday")
   for flooding or heavy rain in Lagos — especially Lekki, Victoria Island, Ikoyi, Lagos Island, Ajah, Oniru, Admiralty Way,
   Lekki–Epe Expressway. Try Punch, Vanguard, Guardian NG, Premium Times, Channels TV, Nairametrics, Pulse, BusinessDay, LASEMA,
   @tokunbowahab / Lagos State Ministry of Environment.
2. **Append** any findings to `events/lagos-2024-07-03/evidence.geojson` using exactly the Task 03 schema
   (`docs/tasks/03-media-evidence.md`). Rules:
   - New ids continue from the current maximum (`ev-063`, …). **Do not renumber, reorder, edit or delete existing features** — several
     carry hand corrections (`geocode_method` starting `review:`).
   - Read the file fresh immediately before writing, write once, and don't leave any background process that rewrites it later.
   - Geocode with the fixed `pipeline/geocode.py` (place-type filtering, area hints). Low-confidence placement is fine; wrong placement is not.
   - Add new sources to `event.json` `sources`.
3. A **negative result is a valid result**: if nothing describes flooding on 2 July, say so and list what you searched.
4. Finish with: what you found (or didn't), features added (ids), sources added. Don't touch `src/`. Don't commit.
