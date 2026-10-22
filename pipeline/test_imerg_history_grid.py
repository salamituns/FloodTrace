#!/usr/bin/env python3
"""Unit tests for the incremental merge in imerg_history_grid.py (Task 47).

The real IMERG fetch needs Earthdata credentials and is never run here (the
task forbids trying); merge_grid_history is a pure function, so it is tested
with synthetic data.
"""

from __future__ import annotations

import copy
import json
import unittest

from imerg_history_grid import last_committed_day, merge_grid_history


def make_cell(totals: list, peaks: list) -> dict:
    return {"total_mm": list(totals), "max_30min_mm_h": list(peaks)}


def old_payload() -> dict:
    """Two cells, 2026-10-15 .. 2026-10-21, exactly as the committed file."""
    return {
        "meta": {
            "retrieved_at": "2026-10-22T13:03:58Z",
            "cells": [
                {"id": "c6.45N3.35E", "lon": 3.35, "lat": 6.45, "place": "Apapa"},
                {"id": "c6.45N3.45E", "lon": 3.45, "lat": 6.45, "place": "Lekki Phase 1"},
            ],
        },
        "dates": ["2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18",
                  "2026-10-19", "2026-10-20", "2026-10-21"],
        "series": {
            "c6.45N3.35E": make_cell(
                [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            ),
            "c6.45N3.45E": make_cell(
                [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0],
                [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            ),
        },
    }


def new_window() -> tuple:
    """The fetched window: 2026-10-19 .. 2026-10-25 (late data re-fetched)."""
    new_dates = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22",
                 "2026-10-23", "2026-10-24", "2026-10-25"]
    new_series = {
        "c6.45N3.35E": make_cell(
            [5.5, 6.5, 7.5, None, 8.0, None, None],   # corrected late values
            [0.55, 0.65, 0.75, None, 0.8, None, None],
        ),
        "c6.45N3.45E": make_cell(
            [50.0, None, 70.0, 80.0, None, None, None],
            [5.0, None, 7.0, 8.0, None, None, None],
        ),
    }
    return new_dates, new_series


class MergeGridHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old = old_payload()
        self.old_copy = copy.deepcopy(self.old)
        self.merged = merge_grid_history(self.old, *new_window())

    def test_new_values_replace_old_on_overlapping_days(self) -> None:
        cell = self.merged["series"]["c6.45N3.35E"]["total_mm"]
        # 2026-10-19..21 are inside both; the refreshed values win.
        self.assertEqual(cell[4:7], [5.5, 6.5, 7.5])
        peak = self.merged["series"]["c6.45N3.35E"]["max_30min_mm_h"]
        self.assertEqual(peak[4:7], [0.55, 0.65, 0.75])

    def test_missing_new_value_keeps_committed_value(self) -> None:
        # 2026-10-20 for the second cell has no value in the refresh; the
        # committed 60.0 must survive rather than being erased.
        cell = self.merged["series"]["c6.45N3.45E"]["total_mm"]
        self.assertEqual(cell[5], 60.0)
        self.assertEqual(cell[6], 70.0)  # refreshed: new value replaces 70.0 == same

    def test_days_before_the_window_are_byte_identical(self) -> None:
        # the window starts 2026-10-19; 2026-10-15..18 must not change at all
        self.assertEqual(self.merged["dates"][:4], self.old["dates"][:4])
        for cell_id, old_cell in self.old["series"].items():
            merged_cell = self.merged["series"][cell_id]
            for key in ("total_mm", "max_30min_mm_h"):
                old_text = json.dumps(old_cell[key][:4])
                merged_text = json.dumps(merged_cell[key][:4])
                self.assertEqual(old_text, merged_text, cell_id)

    def test_appends_new_days_in_date_order(self) -> None:
        self.assertEqual(
            self.merged["dates"],
            ["2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18",
             "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22",
             "2026-10-23", "2026-10-24", "2026-10-25"],
        )
        cell = self.merged["series"]["c6.45N3.45E"]["total_mm"]
        self.assertEqual(cell[7:], [80.0, None, None, None])

    def test_inputs_are_not_mutated(self) -> None:
        self.assertEqual(self.old, self.old_copy)

    def test_meta_is_carried_over(self) -> None:
        self.assertEqual(self.merged["meta"], self.old["meta"])


class LastCommittedDayTests(unittest.TestCase):
    def test_last_day_with_a_value(self) -> None:
        grid = {
            "dates": ["2026-10-15", "2026-10-16", "2026-10-17"],
            "series": {"a": make_cell([1.0, None, None], [0.1, None, None])},
        }
        from datetime import date

        self.assertEqual(last_committed_day(grid), date(2026, 10, 15))

    def test_no_values_at_all(self) -> None:
        grid = {
            "dates": ["2026-10-15", "2026-10-16"],
            "series": {"a": make_cell([None, None], [None, None])},
        }
        self.assertIsNone(last_committed_day(grid))


if __name__ == "__main__":
    unittest.main()
