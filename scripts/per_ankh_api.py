"""Shared HTTP client for Per-Ankh's public read-only API.

Used by elo-calculator.py and fetch-tournament-matches.py -- both fetch
tournament/match data from the same public endpoints; this is the one place
that logic lives, instead of each script defining its own fetch_json().
"""

import json
import sys
from typing import List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.per-ankh.app/v1"


def fetch_json(url: str, user_agent: str) -> Optional[dict]:
    """Fetch JSON from url. Prints an error and returns None on failure."""
    try:
        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except URLError as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None


def fetch_tournament(slug: str, user_agent: str) -> Optional[dict]:
    """Fetch tournament detail by slug. None if not found or unreachable."""
    return fetch_json(f"{API_BASE}/tournaments/{slug}", user_agent)


def fetch_tournament_matches(tournament_id: str, user_agent: str) -> Optional[List[dict]]:
    """Fetch all matches (any status) for a tournament id. None on fetch
    failure -- distinct from a successful fetch that just found zero matches."""
    data = fetch_json(f"{API_BASE}/tournaments/{tournament_id}/matches", user_agent)
    if data is None:
        return None
    return data.get("matches", [])
