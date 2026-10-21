#!/usr/bin/env python3
"""Collapse near-duplicate search entries (Task 43)."""

from __future__ import annotations

import unittest

from build_search_index import dedup, detail_score


def item(name: str, kind: str, lon: float, lat: float, **extra: object) -> dict:
    row = {"name": name, "kind": kind, "lon": lon, "lat": lat, "alt": [], "area": None}
    row.update(extra)
    return row


class DedupTests(unittest.TestCase):
    def test_same_name_kind_within_600m_even_if_area_differs(self) -> None:
        a = item("Ojuelegba Road", "bridge", 3.3645, 6.5099, area="Ojuelegba")
        b = item(
            "Ojuelegba Road",
            "bridge",
            3.3647,
            6.5100,
            area="Yaba",
            alt=["Ojuelegba Rd bridge"],
        )
        out = dedup([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["area"], "Yaba")
        self.assertIn("Ojuelegba Rd bridge", out[0]["alt"])

    def test_keeps_the_entry_with_more_detail(self) -> None:
        thin = item("Law School", "bus_station", 3.4267, 6.4430, area=None)
        rich = item(
            "Law School",
            "bus_station",
            3.4266,
            6.4431,
            area="Victoria Island",
            alt=["Nigerian Law School"],
        )
        out = dedup([thin, rich])
        self.assertEqual(len(out), 1)
        self.assertGreater(detail_score(out[0]), detail_score(thin))
        self.assertEqual(out[0]["area"], "Victoria Island")

    def test_leaves_same_name_farther_than_600m(self) -> None:
        a = item("Church Street", "street", 3.36, 6.51, area="Yaba")
        b = item("Church Street", "street", 3.45, 6.45, area="Ikoyi")
        self.assertEqual(len(dedup([a, b])), 2)


if __name__ == "__main__":
    unittest.main()
