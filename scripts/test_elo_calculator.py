#!/usr/bin/env python3
"""
Regression tests for elo-calculator.py.

Run: python3 scripts/test_elo_calculator.py
(or: python3 -m unittest scripts.test_elo_calculator, from repo root, once
scripts/ has an __init__.py -- it doesn't, so run this file directly.)

elo-calculator.py isn't importable as a normal module (hyphenated filename),
so it's loaded by path below, same technique used throughout manual testing
in this repo's history for this script.

No external dependencies -- stdlib unittest only, matching the scripts'
"no external dependencies" design principle (see elo-calculator-usage.md).
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # so elo-calculator.py's `from per_ankh_api import ...` resolves


def _load_elo_calculator():
    spec = importlib.util.spec_from_file_location("elo_calculator", os.path.join(SCRIPT_DIR, "elo-calculator.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


elo = _load_elo_calculator()


def make_ref(slug, source="per-ankh", user_id=None, display_name=None):
    return elo.PlayerRef(
        user_id=user_id or f"uid_{slug}",
        slug=slug,
        display_name=display_name or slug,
        source=source,
    )


def make_match(match_id, date, player_a, player_b, winner, origin="live"):
    return elo.CanonicalMatch(
        match_id=match_id, date=date,
        player_a=player_a, player_b=player_b,
        winner=winner, origin=origin,
    )


class TestTransliterate(unittest.TestCase):
    def test_ascii_lowercased(self):
        self.assertEqual(elo.transliterate("Alcaras"), "alcaras")

    def test_homoglyphs_reconstructed(self):
        # The real case that prompted this: a Discord display_name styled
        # with stroke/bar-decorated Latin letters and bird-emoji bookends.
        # "ł" (L WITH STROKE) reads as "l", not the "i" this particular
        # generator intended -- a known, accepted limitation, not a bug.
        self.assertEqual(elo.transliterate("🐦🐦ĐØɄ฿ⱠɆ₵ØⱤVłĐ🐦🐦"), "doublecorvld")

    def test_currency_symbol_overrides(self):
        self.assertEqual(elo.transliterate("฿"), "b")
        self.assertEqual(elo.transliterate("₵"), "c")

    def test_decorative_only_drops_to_empty(self):
        self.assertEqual(elo.transliterate("🐦🐦"), "")


class TestPreferredName(unittest.TestCase):
    def test_real_account_with_slug_uses_slug(self):
        self.assertEqual(elo.preferred_name("alcaras", "Some Display Name", "per-ankh"), "alcaras")

    def test_real_account_no_slug_falls_back_transliterated(self):
        self.assertEqual(elo.preferred_name(None, "ShaunMcNamee", "per-ankh"), "shaunmcnamee")

    def test_synthetic_ignores_its_internal_slug(self):
        # Synthetic players carry a "prospector-nizar"-style internal key in
        # `slug`, which must never be shown -- display_name only.
        self.assertEqual(elo.preferred_name("prospector-nizar", "Nizar", "synthetic"), "nizar")


class TestCalculateRatings(unittest.TestCase):
    def test_equal_ratings_expected_deltas(self):
        calc = elo.ELOCalculator()
        calc.canonical_matches = [make_match("m1", "2025-01-01", make_ref("a"), make_ref("b"), "a")]
        calc.calculate_ratings()
        self.assertAlmostEqual(calc.ratings["uid_a"].rating, 1500 + 32)
        self.assertAlmostEqual(calc.ratings["uid_b"].rating, 1500 - 32)
        self.assertEqual((calc.ratings["uid_a"].wins, calc.ratings["uid_a"].losses), (1, 0))
        self.assertEqual((calc.ratings["uid_b"].wins, calc.ratings["uid_b"].losses), (0, 1))

    def test_match_history_correct_regardless_of_slot(self):
        """Regression: calculate_ratings() once wrote one shared, tautologically
        mis-attributed match_history entry to both players -- opponent always
        showed as the slot_b player, result always showed "W". Here, zophister
        is slot_b in match 1 (loses) and slot_a in match 2 (wins); their own
        history must reflect their own actual opponent and actual result each
        time, not a copy of the other player's."""
        calc = elo.ELOCalculator()
        calc.canonical_matches = [
            make_match("m1", "2025-01-01", make_ref("alcaras"), make_ref("zophister"), "a"),
            make_match("m2", "2025-01-05", make_ref("zophister"), make_ref("boldus"), "a"),
        ]
        calc.calculate_ratings()
        zoph_history = calc.ratings["uid_zophister"].match_history
        self.assertEqual(len(zoph_history), 2)
        self.assertEqual(zoph_history[0]["opponent"], "alcaras")
        self.assertEqual(zoph_history[0]["result"], "L")
        self.assertEqual(zoph_history[1]["opponent"], "boldus")
        self.assertEqual(zoph_history[1]["result"], "W")

    def test_pre_match_rating_correct_regardless_of_slot(self):
        """Regression: print_match() once reconstructed pre-match ratings by
        replaying history, but only credited a player's prior matches when
        they occupied the same slot again -- silently dropping matches played
        from the other slot. rating_before must reflect ALL prior matches."""
        calc = elo.ELOCalculator()
        calc.canonical_matches = [
            make_match("m1", "2025-01-01", make_ref("alcaras"), make_ref("zophister"), "a"),  # zoph loses as slot_b
            make_match("m2", "2025-01-05", make_ref("zophister"), make_ref("boldus"), "a"),   # zoph wins as slot_a
        ]
        calc.calculate_ratings()
        zoph_history = calc.ratings["uid_zophister"].match_history
        # zophister lost match 1 (1500 -> 1468), so match 2's rating_before
        # must be 1468, not the baseline 1500 the old bug would have used.
        self.assertAlmostEqual(zoph_history[1]["rating_before"], zoph_history[0]["rating_after"])
        self.assertNotAlmostEqual(zoph_history[1]["rating_before"], elo.BASELINE_ELO)

    def test_same_date_batch_is_order_independent(self):
        """Regression: two same-date matches sharing a player produced a
        different final rating depending on which order they were listed in
        (1497.06 vs 1502.94 for this exact case) before batching was added."""
        def build(order):
            calc = elo.ELOCalculator()
            m1 = make_match("m1", "2025-01-01", make_ref("zophister"), make_ref("alcaras"), "a")
            m2 = make_match("m2", "2025-01-01", make_ref("zophister"), make_ref("boldus"), "b")
            calc.canonical_matches = [m1, m2] if order == 0 else [m2, m1]
            calc.calculate_ratings()
            return calc.ratings["uid_zophister"].rating

        self.assertAlmostEqual(build(0), build(1))
        # And matches the known-correct value: two wins/losses that cancel out
        # around the same 1500 baseline opponents nets back to ~baseline.
        self.assertAlmostEqual(build(0), elo.BASELINE_ELO, places=1)

    def test_synthetic_player_participates_but_not_ranked(self):
        calc = elo.ELOCalculator()
        calc.canonical_matches = [
            make_match("m1", "2025-01-01", make_ref("alcaras"), make_ref("ghost", source="synthetic"), "a"),
        ]
        calc.calculate_ratings()
        # Synthetic player's match still produced a real delta for the real player.
        self.assertAlmostEqual(calc.ratings["uid_alcaras"].rating, 1500 + 32)
        self.assertIn("uid_ghost", calc.ratings)
        # But synthetic player is excluded from the ranked/leaderboard view.
        ranked_ids = [p.user_id for p in calc.ranked_players()]
        self.assertIn("uid_alcaras", ranked_ids)
        self.assertNotIn("uid_ghost", ranked_ids)


class TestCanonicalFromLive(unittest.TestCase):
    def test_explicit_null_reported_at_does_not_crash(self):
        """Regression: match.get("reported_at", "") returns None (not the
        default) when the key is present with an explicit null, which the
        live API does for some matches -- broke date-sorting with a
        TypeError before this was guarded with `or ""`."""
        calc = elo.ELOCalculator()
        raw = {
            "match_id": "m1", "reported_at": None,
            "slot_a_user_id": "ua", "slot_b_user_id": "ub",
            "slot_a_id": "sa", "slot_b_id": "sb", "winner_slot_id": "sa",
            "slot_a_slug": "a", "slot_b_slug": "b",
        }
        canonical = calc._canonical_from_live(raw)
        self.assertEqual(canonical.date, "")

    def test_missing_slot_user_id_returns_none(self):
        calc = elo.ELOCalculator()
        self.assertIsNone(calc._canonical_from_live({"match_id": "m1"}))


class TestLoadSourceFile(unittest.TestCase):
    def _write(self, data):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir())
        json.dump(data, f)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_valid_file_loads(self):
        path = self._write({
            "players": {
                "a": {"user_id": "uid_a", "slug": "a", "display_name": "A"},
                "b": {"user_id": "uid_b", "slug": "b", "display_name": "B"},
            },
            "matches": [
                {"match_id": "1", "date": "2025-01-01", "player1": "a", "player2": "b", "winner": "a"},
            ],
        })
        calc = elo.ELOCalculator()
        calc.load_source_file(path)
        self.assertEqual(len(calc.canonical_matches), 1)
        self.assertEqual(calc.canonical_matches[0].player_a.user_id, "uid_a")

    def test_match_ids_namespaced_by_filename(self):
        path = self._write({
            "players": {"a": {"user_id": "uid_a", "slug": "a", "display_name": "A"},
                        "b": {"user_id": "uid_b", "slug": "b", "display_name": "B"}},
            "matches": [{"match_id": "1", "date": "2025-01-01", "player1": "a", "player2": "b", "winner": "a"}],
        })
        calc = elo.ELOCalculator()
        calc.load_source_file(path)
        tag = os.path.splitext(os.path.basename(path))[0]
        self.assertEqual(calc.canonical_matches[0].match_id, f"{tag}:1")

    def test_top_level_list_raises_clear_error(self):
        """Regression: feeding elo-calculator.py a fetch-tournament-matches.py
        export (a bare JSON list, not the players+matches schema) crashed
        with AttributeError: 'list' object has no attribute 'get'."""
        path = self._write([{"match_id": "abc", "slot_a_user_id": "x"}])
        calc = elo.ELOCalculator()
        with self.assertRaises(ValueError):
            calc.load_source_file(path)

    def test_missing_players_key_raises(self):
        path = self._write({"matches": []})
        calc = elo.ELOCalculator()
        with self.assertRaises(ValueError):
            calc.load_source_file(path)

    def test_unknown_player_reference_raises(self):
        path = self._write({
            "players": {"a": {"user_id": "uid_a", "slug": "a", "display_name": "A"}},
            "matches": [{"match_id": "1", "date": "2025-01-01", "player1": "a", "player2": "nobody", "winner": "a"}],
        })
        calc = elo.ELOCalculator()
        with self.assertRaises(ValueError):
            calc.load_source_file(path)

    def test_winner_not_matching_either_player_raises(self):
        path = self._write({
            "players": {"a": {"user_id": "uid_a", "slug": "a", "display_name": "A"},
                        "b": {"user_id": "uid_b", "slug": "b", "display_name": "B"}},
            "matches": [{"match_id": "1", "date": "2025-01-01", "player1": "a", "player2": "b", "winner": "someone_else"}],
        })
        calc = elo.ELOCalculator()
        with self.assertRaises(ValueError):
            calc.load_source_file(path)


class TestFindPlayer(unittest.TestCase):
    def _calc(self):
        calc = elo.ELOCalculator()
        calc.canonical_matches = [make_match("m1", "2025-01-01", make_ref("alcaras"), make_ref("auro"), "a")]
        calc.calculate_ratings()
        return calc

    def test_find_by_slug(self):
        self.assertIsNotNone(self._calc().find_player("alcaras"))

    def test_find_by_user_id(self):
        self.assertIsNotNone(self._calc().find_player("uid_alcaras"))

    def test_find_by_display_name_case_insensitive(self):
        calc = elo.ELOCalculator()
        calc.canonical_matches = [make_match(
            "m1", "2025-01-01",
            make_ref("nizar-key", source="synthetic", user_id="prospector:nizar", display_name="Nizar"),
            make_ref("alcaras"), "a",
        )]
        calc.calculate_ratings()
        self.assertIsNotNone(calc.find_player("nizar"))
        self.assertIsNotNone(calc.find_player("Nizar"))

    def test_ambiguous_match_returns_none(self):
        calc = elo.ELOCalculator()
        calc.canonical_matches = [
            make_match("m1", "2025-01-01",
                       make_ref("dup1", source="synthetic", user_id="uid_dup1", display_name="Duplicate"),
                       make_ref("alcaras"), "a"),
            make_match("m2", "2025-01-02",
                       make_ref("dup2", source="synthetic", user_id="uid_dup2", display_name="Duplicate"),
                       make_ref("auro"), "a"),
        ]
        calc.calculate_ratings()
        self.assertIsNone(calc.find_player("Duplicate"))

    def test_not_found_returns_none(self):
        self.assertIsNone(self._calc().find_player("nobody-here"))


class TestHeadToHead(unittest.TestCase):
    def _calc(self):
        calc = elo.ELOCalculator()
        calc.canonical_matches = [
            # alcaras beats zophister twice, loses once, in different slots.
            make_match("m1", "2025-01-01", make_ref("alcaras"), make_ref("zophister"), "a"),
            make_match("m2", "2025-01-05", make_ref("zophister"), make_ref("alcaras"), "b"),
            make_match("m3", "2025-01-10", make_ref("zophister"), make_ref("alcaras"), "a"),
            # A match against a third player must not count toward the h2h.
            make_match("m4", "2025-01-15", make_ref("alcaras"), make_ref("boldus"), "a"),
        ]
        calc.calculate_ratings()
        return calc

    def test_record_and_winner_correct_regardless_of_slot(self):
        calc = self._calc()
        pa = calc.find_player("alcaras")
        pb = calc.find_player("zophister")
        ids = {pa.user_id, pb.user_id}
        matches = sorted(
            (m for m in calc.canonical_matches if {m.player_a.user_id, m.player_b.user_id} == ids),
            key=lambda m: m.date,
        )
        self.assertEqual(len(matches), 3)

        def pa_won(m):
            winner_ref = m.player_a if m.winner == "a" else m.player_b
            return winner_ref.user_id == pa.user_id

        self.assertEqual(sum(1 for m in matches if pa_won(m)), 2)

    def test_third_player_matches_excluded(self):
        calc = self._calc()
        pa = calc.find_player("alcaras")
        pb = calc.find_player("zophister")
        ids = {pa.user_id, pb.user_id}
        matches = [m for m in calc.canonical_matches if {m.player_a.user_id, m.player_b.user_id} == ids]
        match_ids = {m.match_id for m in matches}
        self.assertNotIn("m4", match_ids)

    def test_unknown_player_returns_none_via_find_player(self):
        calc = self._calc()
        self.assertIsNone(calc.find_player("nobody-here"))

    def test_expected_score_matches_calculate_expected_score(self):
        calc = self._calc()
        pa = calc.find_player("alcaras")
        pb = calc.find_player("zophister")
        expected_a = calc.calculate_expected_score(pa.rating, pb.rating)
        expected_b = calc.calculate_expected_score(pb.rating, pa.rating)
        self.assertAlmostEqual(expected_a + expected_b, 1.0)
        # alcaras won 2 of 3 meetings, so should be rated (and favored) higher.
        self.assertGreater(pa.rating, pb.rating)
        self.assertGreater(expected_a, 0.5)


class TestExportSnapshotRoundTrip(unittest.TestCase):
    def test_export_then_reload_matches_original_ratings(self):
        original = elo.ELOCalculator("test-tournament")
        original.canonical_matches = [
            make_match("m1", "2025-01-01", make_ref("alcaras"), make_ref("auro"), "a", origin="live"),
            make_match("m2", "2025-01-05", make_ref("auro"), make_ref("boldus"), "b", origin="live"),
        ]
        original.calculate_ratings()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "snapshot.json")
            original.export_snapshot(path)

            reloaded = elo.ELOCalculator()
            reloaded.load_source_file(path)
            reloaded.calculate_ratings()

        for user_id, player in original.ratings.items():
            self.assertIn(user_id, reloaded.ratings)
            self.assertAlmostEqual(player.rating, reloaded.ratings[user_id].rating)


if __name__ == "__main__":
    unittest.main()
