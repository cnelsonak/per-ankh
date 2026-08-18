#!/usr/bin/env python3
"""
ELO rating calculator for Per-Ankh tournaments.

Usage:
    python3 elo-calculator.py [--tournament <slug>] [--source <file> ...] [--no-live] leaderboard
    python3 elo-calculator.py [--tournament <slug>] [--source <file> ...] [--no-live] match <match_id>
    python3 elo-calculator.py [--tournament <slug>] [--source <file> ...] [--no-live] player <player_slug|user_id>
    python3 elo-calculator.py [--tournament <slug>] [--source <file> ...] [--no-live] export <json|csv|snapshot>

By default, fetches the live Per-Ankh tournament (--tournament, default
2026-community-tournament) and replays it chronologically to compute ELO.

--source <file> replays an additional historical match snapshot (the same
portable schema `export snapshot` produces -- see scripts/data/) alongside
the live tournament; repeat the flag to layer in more than one file. All
loaded matches, live and file-sourced alike, are merged and replayed in a
single chronological pass, so historical results feed directly into
players' current ratings.

--no-live skips the live fetch entirely (requires at least one --source),
for pure offline replay over snapshot files.

`export snapshot` writes the live-fetched tournament's raw matches to that
same portable schema, so a future run can replay it via --source without
re-querying the API.
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.per-ankh.app/v1"

# ELO Configuration (locked from design decisions)
BASELINE_ELO = 1500
K_FACTOR = 64  # Fixed; future iterations may vary by match type
TOURNAMENT_SLUG = "2026-community-tournament"


# A handful of "fancy text generator" substitutions with no Latin-letter name
# to fall back on (transliterate() below handles the far more common case --
# stroke/bar/tail-decorated Latin letters like D-with-stroke -- generically).
# Output is always lowercase, so case doesn't matter here.
_HOMOGLYPH_OVERRIDES = {
    "฿": "b",  # THAI CURRENCY SYMBOL BAHT, used as a B lookalike
    "₵": "c",  # CEDI SIGN, used as a C lookalike
}


def transliterate(text: str) -> str:
    """Best-effort transliteration of Unicode "fancy font" homoglyphs (Discord
    display names built from stroke/bar/tail Latin-letter variants and the odd
    currency symbol standing in for a letter) to lowercase plain ASCII.
    Decorative characters with no letter equivalent (emoji, symbols) are
    dropped rather than left as mojibake. Not a full Unicode confusables
    table -- covers the patterns actually seen in Per-Ankh display names,
    generically by reading each character's Unicode name rather than a
    hardcoded per-name mapping."""
    out = []
    for ch in text:
        if ch.isascii():
            out.append(ch.lower())
            continue
        if ch in _HOMOGLYPH_OVERRIDES:
            out.append(_HOMOGLYPH_OVERRIDES[ch])
            continue
        m = re.search(r"LETTER ([A-Z])\b", unicodedata.name(ch, ""))
        if m:
            out.append(m.group(1).lower())
        # else: no plain-letter equivalent (emoji, decorative symbols) -- drop
    return "".join(out)


def preferred_name(slug: Optional[str], display_name: str, source: str) -> str:
    """The name to show for a player. A real account's slug is Per-Ankh's own
    authoritative, always-lowercase identifier -- shown directly. Everyone
    else -- synthetic identities (whose "slug" is only an internal namespacing
    key, e.g. "prospector-nizar") and real accounts with no slug (falling back
    to a raw Discord display_name, occasionally full of "fancy font"
    homoglyphs) -- is shown as a transliterated, lowercased display_name, to
    match that same lowercase-slug convention."""
    if source != "synthetic" and slug:
        return slug
    return transliterate(display_name)


@dataclass
class PlayerRef:
    """A player identity as referenced by one side of a match."""
    user_id: str
    slug: Optional[str]
    display_name: str
    source: str = "per-ankh"  # "per-ankh" (real account) or "synthetic" (no account)


@dataclass
class CanonicalMatch:
    """A single decided match, normalized from whatever source produced it."""
    match_id: str
    date: str
    player_a: PlayerRef
    player_b: PlayerRef
    winner: str  # "a" or "b"
    nation_a: Optional[str] = None
    nation_b: Optional[str] = None
    map_name: Optional[str] = None
    origin: str = "live"  # "live" or the --source file's tag


@dataclass
class PlayerRating:
    """A player's ELO rating state."""
    user_id: str
    slug: Optional[str]
    display_name: str
    source: str = "per-ankh"
    rating: float = BASELINE_ELO
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    match_history: List[dict] = field(default_factory=list)

    def __lt__(self, other):
        """Sort by rating (descending), then by name."""
        if abs(self.rating - other.rating) > 0.1:
            return self.rating > other.rating
        return (preferred_name(self.slug, self.display_name, self.source)
                < preferred_name(other.slug, other.display_name, other.source))


class ELOCalculator:
    """Calculate and manage ELO ratings across one or more match sources."""

    def __init__(self, tournament_slug: str = TOURNAMENT_SLUG):
        self.tournament_slug = tournament_slug
        self.tournament_data = {}
        self.canonical_matches: List[CanonicalMatch] = []
        self.ratings: Dict[str, PlayerRating] = {}

    def fetch_json(self, url: str) -> Optional[dict]:
        """Fetch JSON from URL."""
        try:
            req = Request(url, headers={"User-Agent": "Per-Ankh-ELO-Calculator/1.0"})
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode())
        except URLError as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            return None

    def _canonical_from_live(self, match: dict) -> Optional[CanonicalMatch]:
        """Convert one raw Per-Ankh API match into a CanonicalMatch, or None if unusable."""
        slot_a_id = match.get("slot_a_user_id")
        slot_b_id = match.get("slot_b_user_id")
        if not (slot_a_id and slot_b_id):
            return None

        winner_is_a = match.get("winner_slot_id") == match.get("slot_a_id")
        map_name = (match.get("map_script") or "").replace("MAPCLASS_MapScript", "") or None

        return CanonicalMatch(
            match_id=match.get("match_id"),
            date=match.get("reported_at") or "",
            player_a=PlayerRef(slot_a_id, match.get("slot_a_slug"), match.get("slot_a_display_name", "Unknown")),
            player_b=PlayerRef(slot_b_id, match.get("slot_b_slug"), match.get("slot_b_display_name", "Unknown")),
            winner="a" if winner_is_a else "b",
            nation_a=match.get("slot_a_nation"),
            nation_b=match.get("slot_b_nation"),
            map_name=map_name,
        )

    def load_tournament(self) -> bool:
        """Fetch the live tournament's matches and add them to canonical_matches."""
        print(f"Loading tournament: {self.tournament_slug}")

        data = self.fetch_json(f"{API_BASE}/tournaments/{self.tournament_slug}")
        if not data:
            print(f"Tournament '{self.tournament_slug}' not found.", file=sys.stderr)
            return False

        self.tournament_data = data
        tournament_id = data.get("tournament_id")
        print(f"  {data.get('name')} (Status: {data.get('status')})")

        matches_data = self.fetch_json(f"{API_BASE}/tournaments/{tournament_id}/matches")
        if not matches_data:
            print("Failed to fetch matches.", file=sys.stderr)
            return False

        raw_matches = [m for m in matches_data.get("matches", []) if m.get("status") == "complete"]
        added = 0
        for m in raw_matches:
            canonical = self._canonical_from_live(m)
            if canonical:
                self.canonical_matches.append(canonical)
                added += 1
        print(f"  Loaded {added} completed matches\n")

        return True

    def load_source_file(self, path: str) -> None:
        """Load a historical match snapshot (schema: players + matches) from disk.

        Match IDs are namespaced by the file's basename so two source files
        can't collide even if they reuse small integer IDs.
        """
        with open(path) as f:
            data = json.load(f)

        tag = os.path.splitext(os.path.basename(path))[0]
        players = data.get("players", {})

        def ref(key: str) -> PlayerRef:
            p = players.get(key)
            if not p:
                raise ValueError(f"{path}: match references unknown player {key!r}")
            return PlayerRef(p["user_id"], p.get("slug"), p.get("display_name", key), p.get("source", "per-ankh"))

        added = 0
        for m in data.get("matches", []):
            winner_key = m["winner"]
            if winner_key == m["player1"]:
                winner = "a"
            elif winner_key == m["player2"]:
                winner = "b"
            else:
                raise ValueError(f"{path}: match {m.get('match_id')} winner {winner_key!r} is neither player1 nor player2")

            self.canonical_matches.append(CanonicalMatch(
                match_id=f"{tag}:{m.get('match_id', added)}",
                date=m.get("date") or "",
                player_a=ref(m["player1"]),
                player_b=ref(m["player2"]),
                winner=winner,
                nation_a=m.get("nation1"),
                nation_b=m.get("nation2"),
                map_name=m.get("map"),
                origin=tag,
            ))
            added += 1

        print(f"Loaded {added} matches from {path}")

    def calculate_expected_score(self, rating_a: float, rating_b: float) -> float:
        """Calculate expected score for player A given both ratings."""
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    def calculate_elo_delta(self, player_rating: float, opponent_rating: float, result: int) -> float:
        """Calculate ELO change for a player.

        Args:
            player_rating: Player's current rating
            opponent_rating: Opponent's current rating
            result: 1 for win, 0 for loss

        Returns:
            ELO delta (positive or negative)
        """
        expected = self.calculate_expected_score(player_rating, opponent_rating)
        delta = K_FACTOR * (result - expected)
        return delta

    def calculate_ratings(self) -> None:
        """Replay every loaded match, oldest date first, to compute ELO ratings."""
        ordered = sorted(self.canonical_matches, key=lambda m: m.date)

        def get_or_init(ref: PlayerRef) -> PlayerRating:
            if ref.user_id not in self.ratings:
                self.ratings[ref.user_id] = PlayerRating(
                    user_id=ref.user_id, slug=ref.slug,
                    display_name=ref.display_name, source=ref.source,
                )
            return self.ratings[ref.user_id]

        for m in ordered:
            pa, pb = get_or_init(m.player_a), get_or_init(m.player_b)
            a_won = m.winner == "a"

            rating_a, rating_b = pa.rating, pb.rating
            delta_a = self.calculate_elo_delta(rating_a, rating_b, 1 if a_won else 0)
            delta_b = self.calculate_elo_delta(rating_b, rating_a, 0 if a_won else 1)

            pa.rating += delta_a
            pb.rating += delta_b
            pa.matches_played += 1
            pb.matches_played += 1
            if a_won:
                pa.wins += 1
                pb.losses += 1
            else:
                pa.losses += 1
                pb.wins += 1

            name_a = preferred_name(pa.slug, pa.display_name, pa.source)
            name_b = preferred_name(pb.slug, pb.display_name, pb.source)

            pa.match_history.append({
                "match_id": m.match_id, "date": m.date, "opponent": name_b,
                "result": "W" if a_won else "L",
                "rating_before": rating_a, "rating_after": pa.rating,
                "delta": delta_a, "player_id": pa.user_id,
            })
            pb.match_history.append({
                "match_id": m.match_id, "date": m.date, "opponent": name_a,
                "result": "L" if a_won else "W",
                "rating_before": rating_b, "rating_after": pb.rating,
                "delta": delta_b, "player_id": pb.user_id,
            })

    def ranked_players(self) -> List[PlayerRating]:
        """Players eligible for leaderboard/export -- excludes synthetic identities
        (historical opponents with no Per-Ankh account, who haven't signed up for
        the current rating system but whose results still fed real players' ratings)."""
        return sorted(p for p in self.ratings.values() if p.source != "synthetic")

    def print_leaderboard(self, limit: Optional[int] = None) -> None:
        """Print leaderboard sorted by rating."""
        ranked = self.ranked_players()
        if not ranked:
            print("No ratings calculated.")
            return

        if limit:
            ranked = ranked[:limit]

        print("=" * 90)
        print(f"{'Rank':<6} {'Player':<25} {'Rating':<10} {'Record':<12} {'Matches':<8}")
        print("=" * 90)

        for rank, player in enumerate(ranked, 1):
            name = preferred_name(player.slug, player.display_name, player.source)
            record = f"{player.wins}-{player.losses}"
            print(f"{rank:<6} {name:<25} {player.rating:>8.0f}   {record:<12} {player.matches_played:<8}")

        print("=" * 90)

    def print_match(self, match_id: str) -> None:
        """Print details of a single match with ELO impact."""
        match = next((m for m in self.canonical_matches if m.match_id == match_id), None)
        if not match:
            print(f"Match '{match_id}' not found.", file=sys.stderr)
            return

        pa = self.ratings.get(match.player_a.user_id)
        pb = self.ratings.get(match.player_b.user_id)
        hist_a = next((h for h in pa.match_history if h["match_id"] == match_id), None) if pa else None
        hist_b = next((h for h in pb.match_history if h["match_id"] == match_id), None) if pb else None

        if not hist_a or not hist_b:
            print(f"No rating history found for match '{match_id}'.", file=sys.stderr)
            return

        rating_a, delta_a = hist_a["rating_before"], hist_a["delta"]
        rating_b, delta_b = hist_b["rating_before"], hist_b["delta"]
        winner_is_a = match.winner == "a"

        display_a = preferred_name(match.player_a.slug, match.player_a.display_name, match.player_a.source)
        display_b = preferred_name(match.player_b.slug, match.player_b.display_name, match.player_b.source)

        print("\n" + "=" * 80)
        print(f"Match: {match_id}")
        print(f"Date: {match.date or 'N/A'}")
        print("=" * 80)

        print(f"\n{display_a:<30} vs {display_b:<30}")
        print(f"{match.nation_a or 'N/A':<30} vs {match.nation_b or 'N/A':<30}")
        print(f"Map: {match.map_name or 'N/A'}")

        print("\n" + "-" * 80)
        print(f"{'Player':<30} {'Rating (Before)':<20} {'Delta':<15} {'Rating (After)':<15}")
        print("-" * 80)

        winner_marker = " (WINNER)" if winner_is_a else ""
        loser_marker = " (WINNER)" if not winner_is_a else ""

        print(f"{display_a + winner_marker:<30} {rating_a:>8.0f}      {delta_a:>+8.1f}      {rating_a + delta_a:>8.0f}")
        print(f"{display_b + loser_marker:<30} {rating_b:>8.0f}      {delta_b:>+8.1f}      {rating_b + delta_b:>8.0f}")
        print("-" * 80)

    def find_player(self, identifier: str) -> Optional[PlayerRating]:
        """Resolve a player by slug, display name, or raw user_id. Slug/display-name
        matching is case-insensitive against both the raw and transliterated forms,
        since what's actually displayed (see preferred_name) can differ from the
        stored display_name -- lowercased for synthetic players, transliterated
        from "fancy font" homoglyphs for real accounts with no slug."""
        if identifier in self.ratings:
            return self.ratings[identifier]

        needle = identifier.lower()
        matches = [
            p for p in self.ratings.values()
            if needle in {n.lower() for n in (p.slug, p.display_name, transliterate(p.display_name)) if n}
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"'{identifier}' matches multiple players without a unique slug:", file=sys.stderr)
            for p in matches:
                print(f"  {p.user_id}  ({p.display_name})", file=sys.stderr)
            print("Use one of the user_ids above to disambiguate.", file=sys.stderr)
        return None

    def print_player(self, identifier: str) -> None:
        """Print player's full match history with ELO progression."""
        player = self.find_player(identifier)
        if not player:
            print(f"Player '{identifier}' not found. Use the slug shown on the leaderboard.", file=sys.stderr)
            return

        user_id = player.user_id
        name = preferred_name(player.slug, player.display_name, player.source)

        print("\n" + "=" * 100)
        print(f"Player: {name} ({user_id})")
        print(f"Final Rating: {player.rating:.0f}  |  Record: {player.wins}-{player.losses}  |  Matches: {player.matches_played}")
        print("=" * 100)

        if not player.match_history:
            print("No matches found.")
            return

        print(f"\n{'#':<4} {'Date':<20} {'Opponent':<25} {'Result':<8} {'Before':<10} {'After':<10} {'Delta':<10}")
        print("-" * 100)

        for idx, hist in enumerate(player.match_history, 1):
            date = hist.get("date", "N/A").split()[0] if hist.get("date") else "N/A"
            opponent = hist.get("opponent", "Unknown")[:24]
            result = hist.get("result", "?")
            before = hist.get("rating_before", 0)
            after = hist.get("rating_after", 0)
            delta = hist.get("delta", 0)

            print(f"{idx:<4} {date:<20} {opponent:<25} {result:<8} {before:>8.0f}  {after:>8.0f}  {delta:>+7.1f}")

        print("=" * 100)

    def export_json(self, filename: Optional[str] = None) -> None:
        """Export the leaderboard (real accounts only) to JSON."""
        if not filename:
            filename = f"elo_ratings_{self.tournament_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        data = {
            "tournament": self.tournament_data,
            "generated_at": datetime.now().isoformat(),
            "ratings": [
                {
                    "user_id": p.user_id,
                    "slug": p.slug,
                    "display_name": p.display_name,
                    "rating": round(p.rating, 1),
                    "matches_played": p.matches_played,
                    "wins": p.wins,
                    "losses": p.losses,
                    "match_history": p.match_history,
                }
                for p in self.ranked_players()
            ]
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Exported to {filename}")

    def export_csv(self, filename: Optional[str] = None) -> None:
        """Export the leaderboard (real accounts only) to CSV."""
        if not filename:
            filename = f"elo_leaderboard_{self.tournament_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Rank", "User ID", "Slug", "Display Name", "Rating", "Matches", "Wins", "Losses"])

            for rank, player in enumerate(self.ranked_players(), 1):
                writer.writerow([
                    rank,
                    player.user_id,
                    player.slug or "",
                    player.display_name,
                    round(player.rating, 1),
                    player.matches_played,
                    player.wins,
                    player.losses,
                ])

        print(f"Exported to {filename}")

    def export_snapshot(self, filename: Optional[str] = None) -> None:
        """Export the live-fetched tournament's raw matches to the portable
        players+matches schema, so a future run can replay them via --source
        without re-querying the API."""
        live = [m for m in self.canonical_matches if m.origin == "live"]
        if not live:
            print("No live-fetched matches to export (did you pass --no-live?).", file=sys.stderr)
            return

        if not filename:
            filename = f"{self.tournament_slug}-matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        players = {}

        def player_key(ref: PlayerRef) -> str:
            key = ref.slug or ref.user_id
            if key not in players:
                players[key] = {
                    "source": ref.source,
                    "user_id": ref.user_id,
                    "slug": ref.slug,
                    "display_name": ref.display_name,
                }
            return key

        matches = []
        for m in live:
            key_a, key_b = player_key(m.player_a), player_key(m.player_b)
            matches.append({
                "match_id": m.match_id,
                "date": m.date,
                "player1": key_a,
                "nation1": m.nation_a,
                "player2": key_b,
                "nation2": m.nation_b,
                "winner": key_a if m.winner == "a" else key_b,
                "map": m.map_name,
            })

        out = {
            "source": f"https://per-ankh.app/tournaments/{self.tournament_slug}",
            "fetched_at": datetime.now().isoformat(),
            "note": (
                f"Snapshot of live-fetched Per-Ankh tournament '{self.tournament_slug}' matches, "
                "for offline replay via --source without re-querying the API."
            ),
            "players": players,
            "matches": matches,
        }

        with open(filename, "w") as f:
            json.dump(out, f, indent=2)

        print(f"Exported {len(matches)} matches to {filename}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ELO rating calculator for Per-Ankh tournaments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--tournament", default=TOURNAMENT_SLUG,
                         help="Live tournament slug to fetch (default: %(default)s)")
    parser.add_argument("--source", action="append", default=[], metavar="FILE",
                         help="Historical match snapshot file to replay alongside the live "
                              "tournament (repeatable)")
    parser.add_argument("--no-live", action="store_true",
                         help="Skip fetching the live tournament; only replay --source files")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("leaderboard", help="Print the ranked leaderboard")

    p_match = sub.add_parser("match", help="Show a single match's ELO impact")
    p_match.add_argument("match_id")

    p_player = sub.add_parser("player", help="Show a player's match history")
    p_player.add_argument("identifier", help="Player slug or user_id")

    p_export = sub.add_parser("export", help="Export data to a file")
    p_export.add_argument("format", choices=["json", "csv", "snapshot"])

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.no_live and not args.source:
        parser.error("--no-live requires at least one --source file")

    calc = ELOCalculator(args.tournament)

    if not args.no_live:
        if not calc.load_tournament():
            sys.exit(1)

    for path in args.source:
        try:
            calc.load_source_file(path)
        except (OSError, ValueError, KeyError) as e:
            print(f"Error loading source {path}: {e}", file=sys.stderr)
            sys.exit(1)

    calc.calculate_ratings()

    if args.command == "leaderboard":
        calc.print_leaderboard()
    elif args.command == "match":
        calc.print_match(args.match_id)
    elif args.command == "player":
        calc.print_player(args.identifier)
    elif args.command == "export":
        if args.format == "json":
            calc.export_json()
        elif args.format == "csv":
            calc.export_csv()
        elif args.format == "snapshot":
            calc.export_snapshot()


if __name__ == "__main__":
    main()
