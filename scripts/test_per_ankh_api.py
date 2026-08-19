#!/usr/bin/env python3
"""
Tests for per_ankh_api.py.

Run: python3 scripts/test_per_ankh_api.py

Mocks urllib.request.urlopen -- no network calls. Scoped to what's ours to
get wrong: URL construction and the None-vs-[] distinction in
fetch_tournament_matches() (fetch failure vs. genuinely zero matches, which
elo-calculator.py and fetch-tournament-matches.py each handle differently).
Not testing that urlopen itself works.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import per_ankh_api as api


def _mock_response(payload: dict):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    return resp


class TestFetchJson(unittest.TestCase):
    @patch("per_ankh_api.urlopen")
    def test_success_returns_parsed_json(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"ok": True})
        result = api.fetch_json("https://example.test/x", "Test-UA/1.0")
        self.assertEqual(result, {"ok": True})

    @patch("per_ankh_api.urlopen")
    def test_url_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("connection refused")
        result = api.fetch_json("https://example.test/x", "Test-UA/1.0")
        self.assertIsNone(result)

    @patch("per_ankh_api.urlopen")
    def test_request_carries_given_user_agent(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({})
        api.fetch_json("https://example.test/x", "Test-UA/1.0")
        sent_request = mock_urlopen.call_args[0][0]
        self.assertEqual(sent_request.get_header("User-agent"), "Test-UA/1.0")
        self.assertEqual(sent_request.full_url, "https://example.test/x")


class TestFetchTournament(unittest.TestCase):
    @patch("per_ankh_api.fetch_json")
    def test_constructs_tournament_detail_url(self, mock_fetch_json):
        mock_fetch_json.return_value = {"tournament_id": "t1"}
        api.fetch_tournament("my-slug", "Test-UA/1.0")
        mock_fetch_json.assert_called_once_with(f"{api.API_BASE}/tournaments/my-slug", "Test-UA/1.0")

    @patch("per_ankh_api.fetch_json")
    def test_none_on_failure(self, mock_fetch_json):
        mock_fetch_json.return_value = None
        self.assertIsNone(api.fetch_tournament("my-slug", "Test-UA/1.0"))


class TestFetchTournamentMatches(unittest.TestCase):
    @patch("per_ankh_api.fetch_json")
    def test_constructs_matches_url(self, mock_fetch_json):
        mock_fetch_json.return_value = {"matches": []}
        api.fetch_tournament_matches("t1", "Test-UA/1.0")
        mock_fetch_json.assert_called_once_with(f"{api.API_BASE}/tournaments/t1/matches", "Test-UA/1.0")

    @patch("per_ankh_api.fetch_json")
    def test_returns_matches_list_on_success(self, mock_fetch_json):
        mock_fetch_json.return_value = {"matches": [{"match_id": "1"}, {"match_id": "2"}]}
        result = api.fetch_tournament_matches("t1", "Test-UA/1.0")
        self.assertEqual(result, [{"match_id": "1"}, {"match_id": "2"}])

    def test_fetch_failure_and_zero_matches_are_distinct(self):
        """The one behavior worth protecting here: elo-calculator.py treats
        None as "failed to fetch, abort" and [] as "fetched fine, tournament
        just has no matches yet" -- collapsing these (e.g. `data.get("matches",
        []) if data else []`, which both scripts used before the shared
        module existed) would silently turn real fetch failures into
        "0 completed matches" instead of an error."""
        with patch("per_ankh_api.fetch_json", return_value=None):
            failure_result = api.fetch_tournament_matches("t1", "Test-UA/1.0")
        with patch("per_ankh_api.fetch_json", return_value={"matches": []}):
            empty_result = api.fetch_tournament_matches("t1", "Test-UA/1.0")

        self.assertIsNone(failure_result)
        self.assertEqual(empty_result, [])
        self.assertIsNotNone(empty_result)


if __name__ == "__main__":
    unittest.main()
