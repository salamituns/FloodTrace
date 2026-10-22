#!/usr/bin/env python3
"""News quotes stay short (Task 48). Fair use: no article bodies, ≤ 25 words."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quotes import MAX_QUOTE_WORDS, clip_quote


class ClipQuoteTests(unittest.TestCase):
    def test_short_quote_unchanged(self) -> None:
        q = "Residents waded through waist-deep water after the rain."
        self.assertEqual(clip_quote(q), q)
        self.assertLessEqual(len(q.split()), MAX_QUOTE_WORDS)

    def test_empty_and_none(self) -> None:
        self.assertEqual(clip_quote(""), "")
        self.assertIsNone(clip_quote(None))

    def test_lagoon_rise_keeps_place_and_cause(self) -> None:
        raw = (
            "this is coupled with heavy rainfall which the state has been "
            "experiencing on a daily basis since last week, resulting in the "
            "level rise of the Lagos lagoon"
        )
        out = clip_quote(raw)
        self.assertLessEqual(len(out.split()), MAX_QUOTE_WORDS)
        self.assertIn("Lagos lagoon", out)
        self.assertIn("heavy rainfall", out)

    def test_okota_blockage_keeps_place_and_structure(self) -> None:
        raw = (
            "the flooding in his Okota area was huge and caused by the total "
            "blockage of over one kilometre terminating at the communal effort "
            "bridge at Fasheun Drive"
        )
        out = clip_quote(raw)
        self.assertLessEqual(len(out.split()), MAX_QUOTE_WORDS)
        self.assertIn("Okota", out)
        self.assertIn("Fasheun Drive", out)
        self.assertIn("blockage", out)

    def test_island_discharge_keeps_lagoon_rise(self) -> None:
        raw = (
            "this happens when the magnitude of rain is so much on the Island "
            "which is discharged into the Lagoon, the water level of the Lagoon rises"
        )
        out = clip_quote(raw)
        self.assertLessEqual(len(out.split()), MAX_QUOTE_WORDS)
        self.assertIn("Island", out)
        self.assertIn("Lagoon", out)


if __name__ == "__main__":
    unittest.main()
