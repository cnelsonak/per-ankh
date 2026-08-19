#!/usr/bin/env python3
"""
Fetch and explore Per-Ankh tournament matches.

Usage:
    python3 fetch-tournament-matches.py [--tournament <slug>] [--phase <phase>]
        [--division <A|B>] [--status <pending|complete>] [--export]

Exports raw API match objects -- NOT the elo-calculator.py --source schema.
Use `elo-calculator.py export snapshot` to produce a --source-compatible file.
"""

import argparse
import json
import sys
from datetime import datetime

from per_ankh_api import fetch_tournament, fetch_tournament_matches

USER_AGENT = "Per-Ankh-Match-Fetcher/1.0"
DEFAULT_TOURNAMENT = "2026-community-tournament"


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string nicely."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return dt_str


def print_match(match: dict, index: int = None) -> None:
    """Print a single match in readable format."""
    prefix = f"[{index}] " if index is not None else ""

    slot_a = match.get("slot_a_display_name", "Unknown")
    slot_b = match.get("slot_b_display_name", "Unknown")
    status = match.get("status", "unknown").upper()
    winner = match.get("winner_slot_id") == match.get("slot_a_id")

    result = ""
    if status == "COMPLETE":
        result = f" → {slot_a} WON" if winner else f" → {slot_b} WON"

    print(f"{prefix}{slot_a} vs {slot_b} ({status}){result}")

    # Player details
    slot_a_nation = (match.get("slot_a_nation") or "").replace("NATION_", "")
    slot_b_nation = (match.get("slot_b_nation") or "").replace("NATION_", "")
    print(f"  {slot_a_nation} vs {slot_b_nation}")

    # Map
    map_script = (match.get("map_script") or "").replace("MAPCLASS_MapScript", "")
    print(f"  Map: {map_script}")

    # Schedule / Result
    parts = match.get("parts", [])
    if parts:
        for part in parts:
            scheduled = part.get("scheduled_at")
            formatted_time = format_datetime(scheduled)
            casters = part.get("casters", [])
            caster_names = ", ".join(c.get("display_name") for c in casters) if casters else "None scheduled"
            print(f"  Scheduled: {formatted_time}")
            print(f"  Casters: {caster_names}")

            streams = part.get("streams", [])
            if streams:
                for stream in streams:
                    print(f"  Stream: {stream.get('url')}")

    print()


def filter_matches(matches, phase=None, division=None, status=None):
    """Filter matches by phase/division/status; None on any field means no filter on it."""
    return [
        m for m in matches
        if (phase is None or m.get("phase") == phase)
        and (division is None or m.get("division") == division)
        and (status is None or m.get("status") == status)
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and explore Per-Ankh tournament matches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--tournament", default=DEFAULT_TOURNAMENT,
                         help="Tournament slug to fetch (default: %(default)s)")
    parser.add_argument("--phase", choices=["swiss", "championship"], type=str.lower, default=None,
                         help="Filter by phase (default: all)")
    parser.add_argument("--division", choices=["A", "B"], type=str.upper, default=None,
                         help="Filter by division (default: all)")
    parser.add_argument("--status", choices=["pending", "complete"], type=str.lower, default=None,
                         help="Filter by status (default: all)")
    parser.add_argument("--export", action="store_true",
                         help="Export the filtered matches to a timestamped JSON file "
                              "(raw API match objects, not the elo-calculator.py "
                              "--source schema)")
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    print(f"Fetching tournament: {args.tournament}\n")

    tournament = fetch_tournament(args.tournament, USER_AGENT)
    if not tournament:
        print(f"Tournament '{args.tournament}' not found.", file=sys.stderr)
        sys.exit(1)

    tournament_id = tournament.get("tournament_id")
    name = tournament.get("name", "Unknown Tournament")
    status = tournament.get("status", "unknown")

    print(f"Tournament: {name}")
    print(f"Status: {status}")
    print(f"Divisions: {tournament.get('division_a_name')} / {tournament.get('division_b_name')}")
    print()

    print("Fetching matches...")
    matches = fetch_tournament_matches(tournament_id, USER_AGENT)
    if matches is None:
        print("Failed to fetch matches.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(matches)} matches\n")

    if not matches:
        print("No matches found.")
        return

    print("\n" + "=" * 80 + "\n")

    filtered = filter_matches(matches, args.phase, args.division, args.status)

    print(f"Showing {len(filtered)} matches:\n")
    for i, match in enumerate(filtered, 1):
        print_match(match, i)

    if args.export:
        output_file = f"tournament_matches_{args.tournament}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(filtered, f, indent=2)
        print(f"Exported {len(filtered)} matches to {output_file}")


if __name__ == "__main__":
    main()
