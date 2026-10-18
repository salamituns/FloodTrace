# Task 03b — make `pipeline/geocode.py` prefer places over street names

Review of Task 03 found a systematic error: free-text Nominatim queries matched **street names** instead of
neighbourhoods — "Majek" → *Phillip Majek Street, Fagba*; "Abijo" → *Abijo Close, Ikoyi*; "Lekki" → Lekki *town*
near the Free Trade Zone instead of the Lekki peninsula. I corrected 7 features by hand in `evidence.geojson`
(see `meta.review` and each `geocode_method` starting with `review:`). **Don't overwrite those corrections.**

Change `pipeline/geocode.py` so it doesn't happen again:
1. Request `addressdetails=1` and keep only results whose `addresstype`/`type` is a place
   (`suburb`, `neighbourhood`, `quarter`, `village`, `town`, `city_district`, `hamlet`, `residential`) —
   **unless** the location text itself names a road (Expressway, Road, Street, Bridge, Way, Avenue…), in which case accept highway results.
2. Accept an optional LGA/area hint and add it to the query (e.g. `"Majek, Ibeju-Lekki"`); if the result's address doesn't contain the
   hint's LGA, reject it.
3. A small alias table for ambiguous Lagos names, at least: `"Lekki"` → Lekki peninsula (Eti-Osa) with confidence `lga`.
4. Return `None` rather than a weak match; callers then place manually and lower confidence (as the task 03 rules already say).
5. Add a tiny self-test (`python3 pipeline/geocode.py --selftest`) that checks the three examples above no longer resolve to the wrong places
   (Majek must not land in Ifako-Ijaiye; Abijo must not land in Ikoyi). Use the cache; respect 1 req/s.

Don't touch `src/` or `evidence.geojson`. Don't commit. Print the self-test result when done.
