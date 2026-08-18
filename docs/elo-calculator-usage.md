# ELO Rating Calculator & Tournament Tools — Usage Guide

Command-line tools for analyzing and rating Old World tournament matches using the Per-Ankh API.

## Overview

Two companion scripts:

1. **`fetch-tournament-matches.py`** — Explore tournament matches with filtering and export
2. **`elo-calculator.py`** — Calculate ELO ratings and view player/match statistics

No external dependencies required—uses Python 3 stdlib only.

## Quick Start

### Prerequisites

- Python 3.7+
- Internet connection (to reach `api.per-ankh.app`)

### Installation

No installation needed. Just run the scripts from the repo root:

```bash
python3 scripts/fetch-tournament-matches.py
python3 scripts/elo-calculator.py leaderboard
```

---

## fetch-tournament-matches.py

Fetch and explore tournament matches from Per-Ankh.

### Basic Usage

```bash
# Default: 2026 Community Tournament
python3 scripts/fetch-tournament-matches.py

# Specify a different tournament by slug
python3 scripts/fetch-tournament-matches.py 2026-community-tournament
```

The script prompts for filters interactively:

```
Filter by phase? (swiss/championship/all) [all]: all
Filter by division? (A/B/all) [all]: A
Filter by status? (pending/complete/all) [all]: complete
```

### Output

Shows each match with:
- Player names and nations
- Map name
- Scheduled date/time
- Casters assigned
- Stream URLs

```
[1] alcaras vs A_Modern_Major_General (COMPLETE) → alcaras WON
  PERSIA vs CARTHAGE
  Map: InlandSea2
  Scheduled: 2026-07-04 17:00 UTC
  Casters: NestorLN, ShaunMcNamee
  Stream: https://www.youtube.com/@Nestor-c3e
```

### Export Results

After filtering, you can export to JSON:

```
Export to JSON? (y/n) [n]: y
Exported 57 matches to tournament_matches_2026-community-tournament_20260816_120000.json
```

---

## elo-calculator.py

Calculate and analyze ELO ratings for tournament players.

### Command Modes

#### 1. Leaderboard

View all players ranked by final rating:

```bash
python3 scripts/elo-calculator.py leaderboard
```

**Output:**

```
==========================================================================================
Rank   Player                    Rating     Record       Matches 
==========================================================================================
1      alcaras                       1564   2-0          2       
2      auro                          1564   2-0          2       
3      boldus                        1564   2-0          2       
...
57     teuzet                        1436   0-2          2       
==========================================================================================
```

Shows:
- Player rank and slug
- Current ELO rating
- Win-loss record
- Total matches played

#### 2. Single Match

View a specific match with ELO impact:

```bash
python3 scripts/elo-calculator.py match XU_JOJEPkahajm2996JvF
```

**Output:**

```
================================================================================
Match: XU_JOJEPkahajm2996JvF
Date: 2026-07-12 01:27:43
================================================================================

siontific                      vs shaunmcnamee                  
NATION_MAURYA                  vs NATION_PERSIA                 
Map: AridPlateau

--------------------------------------------------------------------------------
Player                         Rating (Before)      Delta           Rating (After) 
--------------------------------------------------------------------------------
siontific (WINNER)                 1500         +32.0          1532
shaunmcnamee                       1500         -32.0          1468
--------------------------------------------------------------------------------
```

Shows:
- Both players and their nations
- Map used
- ELO before and after match
- Rating delta (K-factor effect)
- Winner marked

#### 3. Player Match History

View a player's full tournament progression, by slug (or user_id):

```bash
python3 scripts/elo-calculator.py player siontific
```

**Output:**

```
====================================================================================================
Player: siontific (O-1ONgvfrVql0yVJiATyh)
Final Rating: 1564  |  Record: 2-0  |  Matches: 2
====================================================================================================

#    Date                 Opponent                  Result   Before     After      Delta     
----------------------------------------------------------------------------------------------------
1    2026-07-12           shaunmcnamee              W            1500      1532    +32.0
2    2026-07-18           zophister                 W            1532      1564    +32.0
====================================================================================================
```

Shows:
- Player name and ID
- Final rating and record
- Match-by-match progression
- Opponent names
- Win/loss/delta per match

#### 4. Export to JSON

Export full ratings and match history:

```bash
python3 scripts/elo-calculator.py export json
# Creates: elo_ratings_2026-community-tournament_TIMESTAMP.json
```

Includes tournament metadata, all player ratings, and full match history.

#### 5. Export to CSV

Export leaderboard as CSV for spreadsheets:

```bash
python3 scripts/elo-calculator.py export csv
# Creates: elo_leaderboard_2026-community-tournament_TIMESTAMP.csv
```

**CSV Format:**

```
Rank,User ID,Slug,Display Name,Rating,Matches,Wins,Losses
1,yM6XWYAsnwsur2g22wAo1,alcaras,alcaras,1564.0,2,2,0
2,2YZztdbgRPlQpz5y1WvLh,auro,Auro,1564.0,2,2,0
...
```

---

## Understanding ELO Ratings

### How It Works

The calculator uses the standard ELO rating formula:

1. **Expected Score** — Probability player A beats player B based on ratings:
   ```
   Expected = 1 / (1 + 10^((Rating_B - Rating_A) / 400))
   ```

2. **Rating Change** — Update based on actual result:
   ```
   Delta = K-factor × (Actual - Expected)
   ```

### Configuration

Current settings (locked by design):

- **Baseline Rating:** 1500 (starting rating for new players)
- **K-Factor:** 64 (points per match; higher = more volatile)
- **Formula:** Standard ELO (same as chess, Lichess)

**Example:** Two evenly-rated players (1500 vs 1500)
- Expected score for each: 0.5
- Winner gains: `64 × (1 - 0.5) = +32`
- Loser loses: `64 × (0 - 0.5) = -32`

**Upset Example:** Strong player (1600) vs weak player (1400)
- Strong player expected: 0.76 win probability
- If strong player wins: `+19` (less because expected)
- If weak player wins: `+49` (more because upset)

---

## Common Workflows

### Weekly Leaderboard Update

```bash
# Get current standings
python3 scripts/elo-calculator.py leaderboard

# Export for website
python3 scripts/elo-calculator.py export csv
# Use elo_leaderboard_*.csv in your web page
```

### Track a Player's Progress

```bash
# Check player by slug (user_id also works)
python3 scripts/elo-calculator.py player <player_slug>

# Example: Track siontific through tournament
python3 scripts/elo-calculator.py player siontific
```

### Analyze a Specific Match

```bash
# Look up match and see rating impact
python3 scripts/elo-calculator.py match <match_id>

# Example: Was this an upset?
python3 scripts/elo-calculator.py match XU_JOJEPkahajm2996JvF
```

### Explore Upcoming Matches

```bash
# Browse available matches
python3 scripts/fetch-tournament-matches.py

# When prompted, filter for pending matches
Filter by status? (pending/complete/all) [all]: pending

# See which matches have casters scheduled
```

---

## Troubleshooting

### "Tournament not found"

Tournament slugs are lowercase, hyphenated. Check the Per-Ankh website URL:
- `https://per-ankh.app/tournaments/2026-community-tournament` → slug is `2026-community-tournament`

### "Player not found"

Player must have played at least one completed match. Use the **slug** shown on the leaderboard, e.g. `siontific`. The **user_id** (21-char nanoid) still works too, e.g. `O-1ONgvfrVql0yVJiATyh`.

Slugs are unique per Per-Ankh account, so this is unambiguous. The rare exception is a player with no slug at all — the calculator falls back to matching on `display_name`, which isn't guaranteed unique; if two such players share a display name, the tool will list their user_ids so you can disambiguate.

### "Match not found"

Match ID must be a completed match in the tournament. Use `fetch-tournament-matches.py` to find valid match IDs.

### Network timeout

API may be temporarily unavailable. Retry after a few seconds. The scripts timeout after 10 seconds.

---

## Design & References

For detailed design decisions (K-factor, baseline rating, persistence model, player identity, etc.), see:

**[elo-calculator-design.md](elo-calculator-design.md)**

Includes:
- Rationale for all design choices
- Academic references (Tennis Abstract, Lichess, UC Berkeley)
- Assessment table validating decisions

---

## Future Expansions

### Next Up

Items identified during the initial build session, not yet started:

1. **Shared data-fetch module** — `fetch-tournament-matches.py` and `elo-calculator.py` each define their own `API_BASE`, `fetch_json()`, and tournament-loading logic. Extract into one shared module both scripts import from.
2. **Local match-data cache/importer** — both scripts currently re-fetch and re-parse from the live API on every run. An importer that persists fetched matches to local files would support historical analysis without re-hitting the live API each time, and gives the shared module above something concrete to read/write. This is *match-data* persistence (raw match records) — distinct from the *rating* persistence question already deferred in the design doc (see [Rating Persistence](elo-calculator-design.md#rating-persistence)).
3. **Secondary match-data source** — a second source of match data has been identified, separate from the live tournament API. Before building the importer against it, need to settle:
   - A canonical match schema both sources normalize into
   - A dedup/conflict rule for matches that appear in both sources (how to detect the same match, and which source wins)

### Planned

1. **Multi-tournament ratings** — Aggregate ratings across multiple tournaments
2. **Match-type weighting** — Different weights for user-submitted vs tournament matches
3. **Rating history** — Track rating changes over time / mid-tournament snapshots
4. **Web integration** — API endpoint for live ratings on tournament pages

### Possible

- Head-to-head records (H2H matrices)
- Performance by nation/archetype
- Chart ratings over tournament timeline
- Rating persistence between runs

---

## License

MIT License (same as Per-Ankh). See repository LICENSE.
