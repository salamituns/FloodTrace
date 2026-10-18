# Task 19 — locate the missing drainage structures, then state the cause finding in the dossiers

Context: `docs/LAGOS_PLAN.md` → "Street-level drainage check". Your Task 17 file `events/drainage_sites.json` is good, but
imagery showed three sites aren't placed on the structure itself.

## A. Fix three sites in `events/drainage_sites.json` (read fresh, write once)
1. **oko-oba-canal**: the current line follows Oko Oba Road, not the canal, and OSM has no waterway there. Find the **Oko-Oba
   canal / channel alignment** in Agege (sources: Lagos MoE/Drainage statements and the Oct 2022 8 m expansion notices, news
   photos or videos with recognisable landmarks, Abimbola Awoniyi Estate, Agric Road, the railway, Google/OSM names like "Oko-Oba
   drainage channel", Wikimapia, and LASG drainage master plan PDFs if public). Give a LineString along the channel itself.
2. **sangotedo-channel-notices**: the channels where buildings got contravention notices on 23 Jun 2024. Find their alignment
   (street names in notices or news, the channel's outfall, OSM `waterway` near Sangotedo/Ajiwe/Abijo). If only a neighbourhood is
   findable, say so.
3. **labora**: the current point (3.92, 6.48) falls in forest, so it's wrong. Find where "Labora" in Ibeju-Lekki actually is (estate
   adverts, property listings, church/school addresses, Nominatim variants like "Laboran", "Labora Town"). If it can't be pinned
   down, set `location_confidence: "not_found"`.
Keep the old geometry as `geometry_prev` and record `located_how`. Same open-source and quote rules as Task 03.

## B. Cause framing in the five dossiers (`events/*/dossier.md`)
We're settled on this framing: **heavy rain is the trigger; human drainage failures are the main amplifier of where it floods**
(rain and tide don't separate flood days from no-flood days, `events/flood_vs_noflood.json`; the causes sources name are almost
all drainage, per Task 15). Rewrite each dossier's "Cause (preliminary)" section to:
- state that framing in 2–3 sentences, with the event's own rain facts (don't change any numbers);
- list that event's **named human causes**, each with who claimed it (official / resident / journalist), the site, and a status:
  `imagery supports` / `imagery inconclusive` / `not checked` / `no imagery after event`, taken from the "Street-level drainage
  check" bullets in `LAGOS_PLAN.md` (2024: Alpha Beach supports, Agungi weak support; 2025: Agric works confirmed before the flood);
- say plainly what isn't proven: these are claims plus visible change, not measured drainage capacity.
Touch only the cause section. Don't touch `src/`, `event.json` or `evidence.geojson`. No background processes. Don't commit.
Finish with: per site, old vs new location and confidence; per dossier, the new cause section's word count.
