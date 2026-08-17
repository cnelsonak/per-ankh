#!/usr/bin/env python3
"""
Fetch tournament matches from Per-Ankh production API.
Usage: python3 fetch-tournament-matches.py [tournament_slug]
"""

import json
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime


API_BASE = "https://api.per-ankh.app/v1"


def fetch_json(url: str) -> dict:
    """Fetch JSON from URL, return parsed dict or None on error."""
    try:
        req = Request(url, headers={"User-Agent": "Per-Ankh-Match-Fetcher/1.0"})
        with urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except URLError as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None


def get_tournament_id(slug: str) -> str:
    """Get tournament ID from slug."""
    data = fetch_json(f"{API_BASE}/tournaments/{slug}")
    if not data:
        print(f"Tournament '{slug}' not found.", file=sys.stderr)
        sys.exit(1)
    return data.get("tournament_id")


def fetch_tournament_detail(slug: str) -> dict:
    """Fetch tournament detail by slug."""
    return fetch_json(f"{API_BASE}/tournaments/{slug}") or {}


def fetch_matches(tournament_id: str) -> list:
    """Fetch all matches for a tournament."""
    data = fetch_json(f"{API_BASE}/tournaments/{tournament_id}/matches")
    return data.get("matches", []) if data else []


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string nicely."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
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
    slot_a_nation = match.get("slot_a_nation", "").replace("NATION_", "")
    slot_b_nation = match.get("slot_b_nation", "").replace("NATION_", "")
    print(f"  {slot_a_nation} vs {slot_b_nation}")
    
    # Map
    map_script = match.get("map_script", "").replace("MAPCLASS_MapScript", "")
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


def main():
    # Default to 2026 Community Tournament
    slug = sys.argv[1] if len(sys.argv) > 1 else "2026-community-tournament"
    
    print(f"Fetching tournament: {slug}\n")
    
    # Get tournament detail
    tournament = fetch_tournament_detail(slug)
    if not tournament:
        sys.exit(1)
    
    tournament_id = tournament.get("tournament_id")
    name = tournament.get("name", "Unknown Tournament")
    status = tournament.get("status", "unknown")
    
    print(f"Tournament: {name}")
    print(f"Status: {status}")
    print(f"Divisions: {tournament.get('division_a_name')} / {tournament.get('division_b_name')}")
    print()
    
    # Fetch matches
    print("Fetching matches...")
    matches = fetch_matches(tournament_id)
    print(f"Found {len(matches)} matches\n")
    
    if not matches:
        print("No matches found.")
        return
    
    # Filter options
    phase_filter = input("Filter by phase? (swiss/championship/all) [all]: ").strip().lower() or "all"
    division_filter = input("Filter by division? (A/B/all) [all]: ").strip().upper() or "all"
    status_filter = input("Filter by status? (pending/complete/all) [all]: ").strip().lower() or "all"
    
    print("\n" + "="*80 + "\n")
    
    # Filter and display
    filtered = [
        m for m in matches
        if (phase_filter == "all" or m.get("phase") == phase_filter)
        and (division_filter == "ALL" or m.get("division") == division_filter)
        and (status_filter == "all" or m.get("status") == status_filter)
    ]
    
    print(f"Showing {len(filtered)} matches:\n")
    for i, match in enumerate(filtered, 1):
        print_match(match, i)
    
    # Export option
    export = input("\nExport to JSON? (y/n) [n]: ").strip().lower()
    if export == "y":
        output_file = f"tournament_matches_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(filtered, f, indent=2)
        print(f"Exported {len(filtered)} matches to {output_file}")


if __name__ == "__main__":
    main()
