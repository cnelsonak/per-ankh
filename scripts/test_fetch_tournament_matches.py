#!/usr/bin/env python3
"""
Regression tests for fetch-tournament-matches.py.

Run: python3 scripts/test_fetch_tournament_matches.py

fetch-tournament-matches.py isn't importable as a normal module (hyphenated
filename), so it's loaded by path below -- same technique as
test_elo_calculator.py.
"""

import contextlib
import importlib.util
import io
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # so the script's `from per_ankh_api import ...` resolves


def _load_fetch_script():
    spec = importlib.util.spec_from_file_location(
        "fetch_tournament_matches", os.path.join(SCRIPT_DIR, "fetch-tournament-matches.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = _load_fetch_script()


class TestFormatDatetime(unittest.TestCase):
    def test_valid_iso_string(self):
        self.assertEqual(fetch.format_datetime("2026-07-12T01:27:43Z"), "2026-07-12 01:27 UTC")

    def test_none_returns_na(self):
        self.assertEqual(fetch.format_datetime(None), "N/A")

    def test_empty_string_returns_na(self):
        self.assertEqual(fetch.format_datetime(""), "N/A")

    def test_malformed_string_returned_as_is(self):
        self.assertEqual(fetch.format_datetime("not-a-date"), "not-a-date")


class TestFilterMatches(unittest.TestCase):
    def setUp(self):
        self.matches = [
            {"id": 1, "phase": "swiss", "division": "A", "status": "complete"},
            {"id": 2, "phase": "swiss", "division": "B", "status": "pending"},
            {"id": 3, "phase": "championship", "division": "A", "status": "complete"},
        ]

    def test_no_filters_returns_everything(self):
        self.assertEqual(len(fetch.filter_matches(self.matches)), 3)

    def test_filter_by_phase(self):
        result = fetch.filter_matches(self.matches, phase="swiss")
        self.assertEqual([m["id"] for m in result], [1, 2])

    def test_filter_by_division(self):
        result = fetch.filter_matches(self.matches, division="A")
        self.assertEqual([m["id"] for m in result], [1, 3])

    def test_filter_by_status(self):
        result = fetch.filter_matches(self.matches, status="complete")
        self.assertEqual([m["id"] for m in result], [1, 3])

    def test_combined_filters(self):
        result = fetch.filter_matches(self.matches, phase="swiss", division="A", status="complete")
        self.assertEqual([m["id"] for m in result], [1])

    def test_no_match_returns_empty(self):
        result = fetch.filter_matches(self.matches, phase="championship", division="B")
        self.assertEqual(result, [])


class TestPrintMatch(unittest.TestCase):
    def _run(self, match):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch.print_match(match)
        return buf.getvalue()

    def test_explicit_null_nation_and_map_do_not_crash(self):
        """Regression: match.get("slot_a_nation", "").replace(...) crashed with
        AttributeError when the key was present with an explicit null -- which
        pending matches with no nation/map assigned yet do. Surfaced by
        --status pending --export before the `or ""` guard was added."""
        match = {
            "slot_a_display_name": "alcaras", "slot_b_display_name": "auro",
            "status": "pending", "slot_a_nation": None, "slot_b_nation": None,
            "map_script": None, "winner_slot_id": None, "slot_a_id": None,
        }
        output = self._run(match)  # must not raise
        self.assertIn("alcaras vs auro", output)
        self.assertIn("PENDING", output)

    def test_winner_marked_correctly_for_slot_a(self):
        match = {
            "slot_a_display_name": "alcaras", "slot_b_display_name": "auro",
            "status": "complete", "winner_slot_id": "sa", "slot_a_id": "sa",
            "slot_a_nation": "NATION_ROME", "slot_b_nation": "NATION_EGYPT",
            "map_script": "MAPCLASS_MapScriptDesert",
        }
        output = self._run(match)
        self.assertIn("alcaras WON", output)
        self.assertNotIn("auro WON", output)

    def test_winner_marked_correctly_for_slot_b(self):
        match = {
            "slot_a_display_name": "alcaras", "slot_b_display_name": "auro",
            "status": "complete", "winner_slot_id": "sb", "slot_a_id": "sa",
            "slot_a_nation": "NATION_ROME", "slot_b_nation": "NATION_EGYPT",
            "map_script": "MAPCLASS_MapScriptDesert",
        }
        output = self._run(match)
        self.assertIn("auro WON", output)
        self.assertNotIn("alcaras WON", output)

    def test_pending_match_shows_no_result(self):
        match = {
            "slot_a_display_name": "alcaras", "slot_b_display_name": "auro",
            "status": "pending", "winner_slot_id": None, "slot_a_id": "sa",
            "slot_a_nation": "NATION_ROME", "slot_b_nation": "NATION_EGYPT",
            "map_script": "MAPCLASS_MapScriptDesert",
        }
        output = self._run(match)
        self.assertNotIn("WON", output)


if __name__ == "__main__":
    unittest.main()
