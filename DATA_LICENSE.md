# Data licences

FloodTrace's own derived data (forecast runs, flood-day catalog, site records,
compiled news locations, and other files we produce from the sources below) is
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), except
where a source's own licence is stricter (see FABDEM below).

News quotes stay with their publishers. We keep short excerpts only (≤ 25
words), with a link to the source.

## Upstream sources

| Source | Licence | Attribution |
|---|---|---|
| ECMWF IFS ensemble, via Open-Meteo | CC BY 4.0 | ECMWF IFS © ECMWF, CC BY 4.0 via Open-Meteo |
| NOAA GFS, via Open-Meteo | CC BY 4.0 (Open-Meteo); GFS public domain | GFS © NOAA, via Open-Meteo |
| GloFAS river flow, via Open-Meteo Flood API | CC BY 4.0 | GloFAS © Copernicus Emergency Management Service (CEMS), via Open-Meteo |
| Other Open-Meteo model archives used in comparison | See each row in `events/forecast/model_compare.json` | Credit the model agency and Open-Meteo |
| NASA GPM IMERG rainfall | NASA open data | NASA GPM IMERG |
| EOT20 ocean tide | CC BY 4.0 | EOT20, DGFI-TUM |
| OpenStreetMap | ODbL 1.0 | © OpenStreetMap contributors |
| Copernicus Sentinel-1 and Sentinel-2 | Copernicus open access | Copernicus Sentinel data [year of acquisition] |
| Google Open Buildings | CC BY 4.0 (or ODbL 1.0) | Sirko et al. 2023, arXiv 2310.11622 |
| GHSL built-up | Copernicus / JRC open data | European Commission, GHSL |
| FABDEM (bare-earth DEM) | CC BY-NC-SA 4.0 | FABDEM, University of Bristol / Fathom |
| Esri World Imagery Wayback | Esri imagery terms (live tiles; not stored or redistributed) | Esri World Imagery Wayback (Esri, Maxar, Earthstar Geographics, and the GIS User Community) |
| OpenFreeMap basemap | ODbL (OSM-derived tiles) | © OpenFreeMap contributors, © OpenStreetMap contributors |

## OpenStreetMap-derived files (ODbL)

These files contain OSM-derived data. Share-alike applies if you extract and
redistribute that data:

- `events/search_index.json` — named streets and places for in-browser search
- `events/osm_facilities.geojson` — schools, hospitals, bus stations and the like
- `events/*/drainage_osm.geojson` — drains, canals and water (per mapped flood)
- `events/drainage_sites/*/osm.geojson` — OSM context around each drainage site
- `events/drainage_sites_imagery.json` — OSM context around drainage sites
- `events/drainage_sites_terrain.json` and `events/terrain_check.json` — lagoon outline from OSM relations
- `events/rough_model/roads.json` — named roads near water
- `events/rough_model/building_counts.json` — OSM building footprints per cell
- `events/rough_model/meta.json` — credits the OSM roads and the OpenFreeMap / OSM basemap

Geocodes of news reports use Nominatim (OSM). The compiled flood locations in
`events/flood_days.json` and `events/flood_spots.json` are FloodTrace's own
catalog; they are not an OSM extract.

## Esri World Imagery Wayback

Esri imagery is displayed live from Esri's Wayback service in the visitor's
browser. We do not store or redistribute Esri pixels. Credit under each image
and on the map: Esri World Imagery Wayback (Esri, Maxar, Earthstar
Geographics, and the GIS User Community).

## FABDEM (CC BY-NC-SA 4.0)

FABDEM is CC BY-NC-SA 4.0, not CC BY. Files derived from it carry that
licence:

- `events/terrain/` — terrain maps and the written verdict
- `events/terrain_check.json` — city-wide terrain metrics
- `events/drainage_sites_terrain.json` — the same metrics at each drainage site
- `events/rough_model/` — the 30 m HAND / depression-fill water layers (built on FABDEM)
