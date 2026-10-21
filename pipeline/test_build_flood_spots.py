#!/usr/bin/env python3
"""Depth attribution: a phrase belongs on a spot only with a local reason."""

from __future__ import annotations

import unittest

from build_flood_spots import (
    attribute_report_depths,
    extract_depth_phrases,
    name_in_sentence,
    split_sentences,
)

GUARDIAN = {
    "url": "https://guardian.ng/news/how-lagos-downpour-wreaked-havoc-gridlock/",
    "publisher": "The Guardian Nigeria",
    "areas": [
        "Oshodi",
        "Agege",
        "Lagos Island",
        "Surulere",
        "Ajegunle",
        "Agric, Ikorodu",
    ],
    "impacts": (
        "About two hours of rain from about 8:35 a.m.; flood made major roads "
        "impassable and went into homes and offices; at Agric, Ikorodu, water "
        "on the road to Asolo in Isawo was knee-high."
    ),
    "quote": (
        "The flood in some parts of the city left thousands of residents "
        "stranded as it made many major roads impassable and went into living homes."
    ),
}

SIX_FEET = {
    "url": "https://guardian.ng/news/how-to-save-lagos-from-flood-disasters-others/",
    "publisher": "Guardian NG",
    "areas": ["Ikoyi", "Lekki Peninsula", "Victoria Island"],
    "impacts": (
        "Weekend pounding rains: many homes, shops and roads flooded; residents "
        "scooping water from houses; some relocated property. Flood up to six "
        "feet high over the roads. No fatality reported."
    ),
    "quote": (
        "No fatality has been reported despite the havoc wreaked by the flood, "
        "which was up to six feet high over the roads"
    ),
}


class SplitSentencesTests(unittest.TestCase):
    def test_keeps_am_with_the_clause_and_splits_on_semicolon(self) -> None:
        parts = split_sentences(GUARDIAN["impacts"])
        knee = [p for p in parts if "knee-high" in p.casefold()]
        self.assertEqual(len(knee), 1)
        self.assertIn("Agric, Ikorodu", knee[0])
        self.assertNotIn("8:35", knee[0])


class NameInSentenceTests(unittest.TestCase):
    def test_punctuation_tolerant_full_area_name(self) -> None:
        sent = "at Agric, Ikorodu, water on the road to Asolo in Isawo was knee-high."
        self.assertTrue(name_in_sentence(sent, "Agric, Ikorodu"))
        self.assertFalse(name_in_sentence(sent, "Agege"))
        self.assertFalse(name_in_sentence(sent, "Lagos Island"))


class AttributeReportDepthsTests(unittest.TestCase):
    def test_same_sentence_only_the_named_geocoded_area(self) -> None:
        mentions = [
            {"name": "Agege", "report_area": "Agege"},
            {"name": "Oshodi", "report_area": "Oshodi"},
            {"name": "Agric, Ikorodu", "report_area": "Agric, Ikorodu"},
        ]
        placed, unplaced = attribute_report_depths(GUARDIAN, mentions)
        self.assertEqual(placed[0], [])
        self.assertEqual(placed[1], [])
        self.assertEqual(len(placed[2]), 1)
        row = placed[2][0]
        self.assertEqual(row["phrase"], "knee-high")
        self.assertEqual(row["placed_by"], "same_sentence")
        self.assertIn("knee-high", row["sentence"])
        self.assertIn("Agric, Ikorodu", row["sentence"])
        self.assertEqual(unplaced, [])

    def test_guardian_knee_high_unplaced_when_agric_did_not_geocode(self) -> None:
        mentions = [
            {"name": "Agege", "report_area": "Agege"},
            {"name": "Oshodi", "report_area": "Oshodi"},
            {"name": "Lagos Island", "report_area": "Lagos Island"},
        ]
        placed, unplaced = attribute_report_depths(GUARDIAN, mentions)
        self.assertTrue(all(p == [] for p in placed))
        self.assertEqual(len(unplaced), 1)
        self.assertEqual(unplaced[0]["phrase"], "knee-high")
        self.assertEqual(unplaced[0]["url"], GUARDIAN["url"])
        self.assertEqual(unplaced[0]["reason"], "area_not_geocoded")

    def test_six_feet_unplaced_when_sentence_names_no_area(self) -> None:
        mentions = [
            {"name": "Ikoyi", "report_area": "Ikoyi"},
            {"name": "Lekki", "report_area": "Lekki Peninsula"},
            {"name": "Victoria Island", "report_area": "Victoria Island"},
        ]
        phrases = {p for p, _ in extract_depth_phrases(
            " ".join([SIX_FEET["impacts"], SIX_FEET["quote"]])
        )}
        self.assertIn("up to six feet high", phrases)
        placed, unplaced = attribute_report_depths(SIX_FEET, mentions)
        self.assertTrue(all(p == [] for p in placed))
        self.assertTrue(unplaced)
        self.assertTrue(all(u["reason"] == "no_area_in_sentence" for u in unplaced))
        self.assertTrue(any(u["phrase"] == "up to six feet high" for u in unplaced))

    def test_single_area_places_even_without_the_name_in_the_sentence(self) -> None:
        report = {
            "url": "https://example.test/one-area",
            "publisher": "Test",
            "areas": ["Makoko"],
            "impacts": "Residents waded through waist-deep water after the rain.",
            "quote": "",
        }
        mentions = [{"name": "Makoko", "report_area": "Makoko"}]
        placed, unplaced = attribute_report_depths(report, mentions)
        self.assertEqual(unplaced, [])
        self.assertEqual(len(placed[0]), 1)
        self.assertEqual(placed[0][0]["placed_by"], "single_area")
        self.assertEqual(placed[0][0]["phrase"], "waist-deep")
        self.assertIn("waist-deep", placed[0][0]["sentence"])

    def test_single_area_unplaced_when_that_area_did_not_geocode(self) -> None:
        report = {
            "url": "https://example.test/one-area-miss",
            "publisher": "Test",
            "areas": ["Makoko"],
            "impacts": "Residents waded through waist-deep water after the rain.",
            "quote": "",
        }
        placed, unplaced = attribute_report_depths(report, [])
        self.assertEqual(placed, [])
        self.assertEqual(unplaced[0]["reason"], "area_not_geocoded")


if __name__ == "__main__":
    unittest.main()
