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

`export json`/`export csv`/`leaderboard` only ever list real Per-Ankh accounts — see [Synthetic players](#synthetic-players) below for why some match participants never show up here even though their results counted.

#### 6. Export a Snapshot (for offline replay)

Dump the live-fetched tournament's raw matches to a portable file, so a future run can replay them without hitting the API again:

```bash
python3 scripts/elo-calculator.py export snapshot
# Creates: 2026-community-tournament-matches_TIMESTAMP.json
```

This is the same `players` + `matches` schema described below under **Historical data & multiple sources** — a snapshot is just another source file.

---

## Historical data & multiple sources

By default the calculator fetches one live tournament and computes ratings from it alone. Two flags let it also replay **historical match data from files**, merged with the live tournament into one continuous chronological pass:

`scripts/data/` holds these files locally but is gitignored (matches this repo's convention for fetched/external data — see `backups/` and `Reference` in `.gitignore`), so a fresh clone won't have any. See `scripts/data/README.md` for what's expected to live there and how to get it.

```bash
# Live tournament + one historical file, replayed together in date order
python3 scripts/elo-calculator.py --source scripts/data/prospector-2025-tournament-matches.json leaderboard

# Stack multiple historical files (repeat --source)
python3 scripts/elo-calculator.py --source file1.json --source file2.json leaderboard

# Pure offline replay — skip the live fetch entirely (requires at least one --source)
python3 scripts/elo-calculator.py --no-live --source scripts/data/prospector-2025-tournament-matches.json leaderboard
```

`--source` and `--no-live` work with every command (`leaderboard`, `match`, `player`, `export`), and combine with `--tournament` to pick a different live tournament.

### Source file schema

A source file is a self-contained JSON object — no querying required to replay it:

```json
{
  "source": "https://prospector.fly.dev/",
  "fetched_at": "2026-08-18T01:11:36Z",
  "note": "human-readable provenance notes",
  "players": {
    "<player-key>": {
      "source": "per-ankh" | "synthetic",
      "user_id": "...",
      "slug": "...",
      "display_name": "...",
      "aliases": ["optional", "raw", "spellings", "seen"]
    }
  },
  "matches": [
    {
      "match_id": "...",
      "date": "2026-03-17",
      "player1": "<player-key>",
      "player2": "<player-key>",
      "winner": "<player-key, must equal player1 or player2>",
      "nation1": "optional", "nation2": "optional", "map": "optional"
    }
  ]
}
```

Only `match_id`, `date`, `player1`, `player2`, and `winner` are required per match; everything else is passed through for display (`match` command) but not required. `export snapshot` produces exactly this schema, so **exporting a tournament and later loading it via `--source` is a lossless round-trip** — verified: a live-only leaderboard and a `--no-live --source <its own snapshot>` replay of the same tournament produce byte-identical output.

Match IDs from `--source` files are namespaced by the file's basename (e.g. `prospector-2025-tournament-matches:52`) so two source files can reuse small integer IDs without colliding. Live-tournament match IDs are never prefixed, so existing `match <id>` usage is unaffected when no `--source` is loaded.

### Synthetic players

Historical sources sometimes include players with no Per-Ankh account — someone from an earlier, unaffiliated tournament who never signed up for this rating system. Give them `"source": "synthetic"` in the player entry instead of `"per-ankh"`. Synthetic players:

- **Still fully participate in rating calculation** — their matches produce real ELO deltas for real opponents, exactly like any other match.
- **Never appear on the leaderboard or in `export json`/`export csv`** — they haven't opted into being ranked.
- **Still work with `player <name>` and `match <id>`** — useful for auditing a specific historical result, just not for ranking.
- **Display by `display_name`, not `slug`, lowercased** — a synthetic identity's "slug" (e.g. `prospector-nizar`) is only an internal lookup key to keep it distinct from real accounts; opponent columns show the friendly name lowercased (`nizar`) to match the display convention of real Per-Ankh slugs. `player`/`match` lookups are case-insensitive, so `nizar` and `Nizar` both resolve.

Decided 2026-08-18 — see [elo-calculator-design.md](elo-calculator-design.md) for the full rationale, including how player identity was hand-mapped from a third-party source to real Per-Ankh accounts.

### Display name normalization

A real Per-Ankh account with a slug always displays by that slug (already lowercase, Per-Ankh-enforced). An account with **no** slug falls back to its raw Discord `display_name` — which occasionally uses "fancy font" Unicode homoglyphs (stroke/bar-decorated Latin letters, currency symbols standing in for letters, decorative emoji bookends). Both that case and the synthetic-player case above are normalized the same way: transliterated back to plain ASCII and lowercased, so e.g. `🐦🐦ĐØɄ฿ⱠɆ₵ØⱤVłĐ🐦🐦` displays as `doublecorvld`. This is best-effort, not a full Unicode confusables table — it reads each character's Unicode name (e.g. "LATIN CAPITAL LETTER D WITH STROKE" → `D`) rather than a hand-built per-glyph table, plus a couple of currency-symbol overrides with no letter-name to fall back on; decorative characters with no letter equivalent are dropped. It can occasionally misread a homoglyph (e.g. `ł`, "L WITH STROKE," reads as `l`, not the `i` some fancy-font generators intend), so it's a readability fix, not a guaranteed exact reconstruction of the original name. `player`/`match` lookups match against both the raw and transliterated forms, case-insensitively.

### Chronological replay

All loaded matches — live and file-sourced alike — are sorted by `date` and replayed in one pass, so historical results feed directly into current ratings rather than being layered on afterward. This is why `alcaras`'s rating after a combined replay differs from either source computed alone: it's one continuous history, not two separate tallies added together.

**Not yet implemented:** time-sliced evaluation (e.g. "ratings as of a given date," or restricting replay to a date range). The `date` field on every match makes this a small addition later, but it isn't built yet — currently every loaded match is always included.

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

### Planned

1. **Shared data-fetch module** — `fetch-tournament-matches.py` and `elo-calculator.py` each define their own `API_BASE`, `fetch_json()`, and tournament-loading logic. Extract into one shared module both scripts import from. (Identified during the initial build session, still open.)
2. **Match dedup/conflict rule across sources** — the multi-source replay (see below) has no way to detect the same match appearing in two loaded sources (live API + a `--source` file, or two `--source` files) and would double-count it. Not currently a live risk — the one source file in `scripts/data/` covers an earlier, non-overlapping season — but there's no guard if that stops being true.
3. **Time-sliced evaluation** — ratings as of a given date, or replay restricted to a date range. Every canonical match already carries a `date`; the multi-source replay just doesn't filter on it yet.
4. **Match-type weighting** — Different weights for user-submitted vs tournament matches
5. **Web integration** — API endpoint for live ratings on tournament pages

### Done

- ~~**Local match-data cache/importer**~~ / ~~**Secondary match-data source**~~ / ~~**Multi-tournament ratings**~~ — `--source` (repeatable) replays historical match files alongside the live tournament in one chronological pass, normalized into a common schema; see [Historical data & multiple sources](#historical-data--multiple-sources). `scripts/data/` (gitignored, local-only) is where these live — see its README.
- ~~**Rating persistence between runs**~~ — `export snapshot` writes a live tournament's matches to that same portable schema, so re-running doesn't require re-querying the API.

### Possible

- Head-to-head records (H2H matrices)
- Performance by nation/archetype
- Chart ratings over tournament timeline

---

## License

MIT License (same as Per-Ankh). See repository LICENSE.
