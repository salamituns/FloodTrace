#!/usr/bin/env python3
"""Wayback records describe live tiles; they must not point at stored Esri JPGs."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from site_imagery import (
    mercator_bounds,
    wayback_event_jpgs,
)
from build_sites import wayback_list

REPO = Path(__file__).resolve().parents[1]


class WaybackJpgScanTests(unittest.TestCase):
    def test_flags_dated_chips_under_events(self) -> None:
        found = wayback_event_jpgs({
            "file": "events/drainage_sites/agungi-collector/2020-04-05.jpg",
            "marked_file": "events/drainage_sites/agungi-collector/2020-04-05_marked.jpg",
            "detail": "events/drainage_sites/agungi-collector/2020-04-05_detail1.jpg",
            "sheet": "events/drainage_sites/agungi-collector/contact_sheet.jpg",
        })
        self.assertEqual(len(found), 4)

    def test_allows_sentinel_and_open_buildings(self) -> None:
        found = wayback_event_jpgs({
            "s2": "events/drainage_sites/agungi-collector/s2_2024.jpg",
            "ob": "events/drainage_sites/agungi-collector/ob_2023.jpg",
            "cache": "pipeline/cache/wayback/chips/agungi-collector/2020-04-05.jpg",
        })
        self.assertEqual(found, [])


class WaybackListLiveTests(unittest.TestCase):
    def test_emits_tile_fields_not_event_jpgs(self) -> None:
        rec = {
            "images": [{
                "acq_date": "2020-04-05",
                "file": "pipeline/cache/wayback/chips/agungi-collector/2020-04-05.jpg",
                "marked_file": None,
                "release": 119,
                "zoom": 16,
                "tile_url": (
                    "https://wayback.maptiles.arcgis.com/arcgis/rest/services/"
                    "World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/"
                    "119/{level}/{row}/{col}"
                ),
                "bounds": {
                    "west": 3.51, "south": 6.44, "east": 3.52, "north": 6.45,
                },
                "resolution_m": 0.31,
                "detail_chips": [{
                    "station": "mid",
                    "file": "pipeline/cache/wayback/chips/agungi-collector/"
                            "2020-04-05_detail2.jpg",
                    "release": 119,
                    "zoom": 18,
                    "tile_url": (
                        "https://wayback.maptiles.arcgis.com/arcgis/rest/"
                        "services/World_Imagery/WMTS/1.0.0/default028mm/"
                        "MapServer/tile/119/{level}/{row}/{col}"
                    ),
                    "bounds": {
                        "west": 3.515, "south": 6.446,
                        "east": 3.519, "north": 6.450,
                    },
                    "lon": 3.517, "lat": 6.448,
                }],
            }],
        }
        out = wayback_list(rec)
        self.assertEqual(len(out), 1)
        im = out[0]
        self.assertEqual(im["acq_date"], "2020-04-05")
        self.assertEqual(im["release"], 119)
        self.assertEqual(im["zoom"], 16)
        self.assertIn("{level}", im["tile_url"])
        self.assertEqual(im["bounds"]["west"], 3.51)
        self.assertEqual(im["resolution_m"], 0.31)
        self.assertNotIn("file", im)
        self.assertNotIn("marked_file", im)
        self.assertEqual(im["detail_chips"][0]["station"], "mid")
        self.assertEqual(im["detail_chips"][0]["zoom"], 18)
        self.assertNotIn("file", im["detail_chips"][0])
        self.assertEqual(wayback_event_jpgs({"wayback": out}), [])

    def test_skips_dates_without_a_live_view(self) -> None:
        rec = {"images": [{
            "acq_date": "2018-12-24",
            "file": None,
            "detail_chips": [],
        }]}
        self.assertEqual(wayback_list(rec), [])


class MercatorBoundsTests(unittest.TestCase):
    def test_north_up_aabb_matches_build_chip_rounding(self) -> None:
        # 500 x 500 m chip around a Lagos point, same corners as process_site.
        corners = [
            (3.513, 6.428),
            (3.517, 6.428),
            (3.517, 6.432),
            (3.513, 6.432),
        ]
        b = mercator_bounds(corners, 18)
        self.assertLess(b["west"], b["east"])
        self.assertLess(b["south"], b["north"])
        self.assertAlmostEqual(b["west"], 3.513, places=3)
        self.assertAlmostEqual(b["east"], 3.517, places=3)


class PipelineOutputTests(unittest.TestCase):
    def test_imagery_and_sites_json_reference_no_wayback_jpgs(self) -> None:
        for rel in ("events/drainage_sites_imagery.json", "events/sites.json"):
            data = json.loads((REPO / rel).read_text())
            found = wayback_event_jpgs(data)
            self.assertEqual(found, [], f"{rel} still points at {found[:5]}")


if __name__ == "__main__":
    unittest.main()
