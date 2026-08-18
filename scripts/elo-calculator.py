#!/usr/bin/env python3
"""
ELO rating calculator for Per-Ankh tournaments.

Usage:
    python3 elo-calculator.py leaderboard [--tournament <slug>]
    python3 elo-calculator.py match <match_id> [--tournament <slug>]
    python3 elo-calculator.py player <user_id> [--tournament <slug>]
    python3 elo-calculator.py export <format> [--tournament <slug>]

Supports formats: json, csv
"""

import json
import sys
import csv
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


API_BASE = "https://api.per-ankh.app/v1"

# ELO Configuration (locked from design decisions)
BASELINE_ELO = 1500
K_FACTOR = 64  # Fixed; future iterations may vary by match type
TOURNAMENT_SLUG = "2026-community-tournament"


@dataclass
class PlayerRating:
    """A player's ELO rating state."""
    user_id: str
    slug: Optional[str]
    display_name: str
    rating: float = BASELINE_ELO
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    match_history: List[dict] = field(default_factory=list)
    
    def __lt__(self, other):
        """Sort by rating (descending), then by name."""
        if abs(self.rating - other.rating) > 0.1:
            return self.rating > other.rating
        return (self.slug or self.display_name) < (other.slug or other.display_name)


class ELOCalculator:
    """Calculate and manage ELO ratings for a tournament."""
    
    def __init__(self, tournament_slug: str = TOURNAMENT_SLUG):
        self.tournament_slug = tournament_slug
        self.tournament_id = None
        self.tournament_data = {}
        self.matches = []
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
    
    def load_tournament(self) -> bool:
        """Load tournament metadata and matches."""
        print(f"Loading tournament: {self.tournament_slug}")
        
        # Fetch tournament detail
        data = self.fetch_json(f"{API_BASE}/tournaments/{self.tournament_slug}")
        if not data:
            print(f"Tournament '{self.tournament_slug}' not found.", file=sys.stderr)
            return False
        
        self.tournament_data = data
        self.tournament_id = data.get("tournament_id")
        
        print(f"  {data.get('name')} (Status: {data.get('status')})")
        
        # Fetch matches
        matches_data = self.fetch_json(f"{API_BASE}/tournaments/{self.tournament_id}/matches")
        if not matches_data:
            print("Failed to fetch matches.", file=sys.stderr)
            return False
        
        self.matches = [m for m in matches_data.get("matches", []) if m.get("status") == "complete"]
        print(f"  Loaded {len(self.matches)} completed matches\n")
        
        return True
    
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
        """Calculate ELO ratings from all completed matches."""
        # Initialize players from matches
        for match in self.matches:
            for key in ["slot_a", "slot_b"]:
                user_id = match.get(f"{key}_user_id")
                slug = match.get(f"{key}_slug")
                display_name = match.get(f"{key}_display_name", "Unknown")
                
                if user_id and user_id not in self.ratings:
                    self.ratings[user_id] = PlayerRating(
                        user_id=user_id,
                        slug=slug,
                        display_name=display_name
                    )
        
        # Process matches in order
        for match in self.matches:
            reported_at = match.get("reported_at", "")
            
            slot_a_id = match.get("slot_a_user_id")
            slot_b_id = match.get("slot_b_user_id")
            winner_id = match.get("winner_slot_id") == match.get("slot_a_id")
            
            if not (slot_a_id and slot_b_id):
                continue
            
            rating_a = self.ratings[slot_a_id].rating
            rating_b = self.ratings[slot_b_id].rating
            
            # Calculate deltas
            delta_a = self.calculate_elo_delta(rating_a, rating_b, 1 if winner_id else 0)
            delta_b = self.calculate_elo_delta(rating_b, rating_a, 0 if winner_id else 1)
            
            # Update ratings
            self.ratings[slot_a_id].rating += delta_a
            self.ratings[slot_b_id].rating += delta_b
            self.ratings[slot_a_id].matches_played += 1
            self.ratings[slot_b_id].matches_played += 1
            
            if winner_id:
                self.ratings[slot_a_id].wins += 1
                self.ratings[slot_b_id].losses += 1
            else:
                self.ratings[slot_a_id].losses += 1
                self.ratings[slot_b_id].wins += 1
            
            # Record match history (separate entries: each is from that player's own perspective)
            slot_a_name = self.ratings[slot_a_id].slug or self.ratings[slot_a_id].display_name
            slot_b_name = self.ratings[slot_b_id].slug or self.ratings[slot_b_id].display_name

            self.ratings[slot_a_id].match_history.append({
                "match_id": match.get("match_id"),
                "date": reported_at,
                "opponent": slot_b_name,
                "result": "W" if winner_id else "L",
                "rating_before": rating_a,
                "rating_after": self.ratings[slot_a_id].rating,
                "delta": delta_a,
                "player_id": slot_a_id,
            })
            self.ratings[slot_b_id].match_history.append({
                "match_id": match.get("match_id"),
                "date": reported_at,
                "opponent": slot_a_name,
                "result": "L" if winner_id else "W",
                "rating_before": rating_b,
                "rating_after": self.ratings[slot_b_id].rating,
                "delta": delta_b,
                "player_id": slot_b_id,
            })
    
    def print_leaderboard(self, limit: Optional[int] = None) -> None:
        """Print leaderboard sorted by rating."""
        if not self.ratings:
            print("No ratings calculated.")
            return
        
        sorted_ratings = sorted(self.ratings.values())
        if limit:
            sorted_ratings = sorted_ratings[:limit]
        
        print("=" * 90)
        print(f"{'Rank':<6} {'Player':<25} {'Rating':<10} {'Record':<12} {'Matches':<8}")
        print("=" * 90)
        
        for rank, player in enumerate(sorted_ratings, 1):
            name = player.slug or player.display_name
            record = f"{player.wins}-{player.losses}"
            print(f"{rank:<6} {name:<25} {player.rating:>8.0f}   {record:<12} {player.matches_played:<8}")
        
        print("=" * 90)
    
    def print_match(self, match_id: str) -> None:
        """Print details of a single match with ELO impact."""
        # Find match
        match = None
        for m in self.matches:
            if m.get("match_id") == match_id:
                match = m
                break
        
        if not match:
            print(f"Match '{match_id}' not found.", file=sys.stderr)
            return
        
        slot_a_id = match.get("slot_a_user_id")
        slot_b_id = match.get("slot_b_user_id")
        
        if not (slot_a_id and slot_b_id):
            print("Match has invalid player IDs.", file=sys.stderr)
            return
        
        slot_a_name = match.get("slot_a_display_name", "Unknown")
        slot_b_name = match.get("slot_b_display_name", "Unknown")
        slot_a_slug = match.get("slot_a_slug")
        slot_b_slug = match.get("slot_b_slug")
        winner_is_a = match.get("winner_slot_id") == match.get("slot_a_id")

        # Pull this match's before/delta straight from each player's own history
        # (calculate_ratings() already replayed all matches chronologically).
        hist_a = next((h for h in self.ratings[slot_a_id].match_history if h["match_id"] == match_id), None)
        hist_b = next((h for h in self.ratings[slot_b_id].match_history if h["match_id"] == match_id), None)

        if not hist_a or not hist_b:
            print(f"No rating history found for match '{match_id}'.", file=sys.stderr)
            return

        rating_a, delta_a = hist_a["rating_before"], hist_a["delta"]
        rating_b, delta_b = hist_b["rating_before"], hist_b["delta"]
        
        print("\n" + "=" * 80)
        print(f"Match: {match_id}")
        print(f"Date: {match.get('reported_at', 'N/A')}")
        print("=" * 80)
        
        display_a = f"{slot_a_slug or slot_a_name}"
        display_b = f"{slot_b_slug or slot_b_name}"
        
        print(f"\n{display_a:<30} vs {display_b:<30}")
        print(f"{match.get('slot_a_nation', 'N/A'):<30} vs {match.get('slot_b_nation', 'N/A'):<30}")
        print(f"Map: {match.get('map_script', 'N/A').replace('MAPCLASS_MapScript', '')}")
        
        print("\n" + "-" * 80)
        print(f"{'Player':<30} {'Rating (Before)':<20} {'Delta':<15} {'Rating (After)':<15}")
        print("-" * 80)
        
        winner_marker = " (WINNER)" if winner_is_a else ""
        loser_marker = " (WINNER)" if not winner_is_a else ""
        
        print(f"{display_a + winner_marker:<30} {rating_a:>8.0f}      {delta_a:>+8.1f}      {rating_a + delta_a:>8.0f}")
        print(f"{display_b + loser_marker:<30} {rating_b:>8.0f}      {delta_b:>+8.1f}      {rating_b + delta_b:>8.0f}")
        print("-" * 80)
    
    def print_player(self, user_id: str) -> None:
        """Print player's full match history with ELO progression."""
        if user_id not in self.ratings:
            print(f"Player '{user_id}' not found.", file=sys.stderr)
            return
        
        player = self.ratings[user_id]
        name = player.slug or player.display_name
        
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
        """Export ratings to JSON."""
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
                for p in sorted(self.ratings.values())
            ]
        }
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"Exported to {filename}")
    
    def export_csv(self, filename: Optional[str] = None) -> None:
        """Export leaderboard to CSV."""
        if not filename:
            filename = f"elo_leaderboard_{self.tournament_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Rank", "User ID", "Slug", "Display Name", "Rating", "Matches", "Wins", "Losses"])
            
            for rank, player in enumerate(sorted(self.ratings.values()), 1):
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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    tournament = TOURNAMENT_SLUG
    
    # Parse tournament override
    if "--tournament" in sys.argv:
        idx = sys.argv.index("--tournament")
        if idx + 1 < len(sys.argv):
            tournament = sys.argv[idx + 1]
    
    calc = ELOCalculator(tournament)
    
    if not calc.load_tournament():
        sys.exit(1)
    
    calc.calculate_ratings()
    
    if command == "leaderboard":
        calc.print_leaderboard()
    
    elif command == "match":
        if len(sys.argv) < 3:
            print("Usage: elo-calculator.py match <match_id>", file=sys.stderr)
            sys.exit(1)
        match_id = sys.argv[2]
        calc.print_match(match_id)
    
    elif command == "player":
        if len(sys.argv) < 3:
            print("Usage: elo-calculator.py player <user_id>", file=sys.stderr)
            sys.exit(1)
        user_id = sys.argv[2]
        calc.print_player(user_id)
    
    elif command == "export":
        if len(sys.argv) < 3:
            print("Usage: elo-calculator.py export <json|csv>", file=sys.stderr)
            sys.exit(1)
        format_type = sys.argv[2].lower()
        if format_type == "json":
            calc.export_json()
        elif format_type == "csv":
            calc.export_csv()
        else:
            print(f"Unknown format: {format_type}", file=sys.stderr)
            sys.exit(1)
    
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
