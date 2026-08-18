# ELO Calculator Design Decisions

This document captures design decisions for the tournament ELO rating calculator built into the match fetching scripts.

## Baseline Rating

**Decision:** 1500

**Rationale:**
- Symmetric midpoint allows ratings to move equally above/below average
- Established precedent in rating systems (Lichess, chess ratings)
- Provides good skill differentiation across natural range (~1000-2000+)
- Feels psychologically neutral (represents "average" player, not arbitrary)

**Alternatives considered:**
- 1600: Slightly elevated baseline, used in USCF chess. Less symmetric.
- 1000: Simpler but arbitrary. Skews visual perception downward.

---

## K-Factor (Points per Match)

**Decision:** K=64 (fixed, no variation by experience)

**Rationale:**
- Limited match count (~5 per player in Swiss format) requires higher K for meaningful differentiation
- Early-stage rating system benefits from faster convergence
- K=64 gives 2x movement vs standard K=32, enabling visible rating changes from tournament results
- Still stable enough to avoid wild swings (K=64 is conservative vs K=128+)
- Evenly matched players: winner gains ~32, loser loses ~32 points per match

**Alternatives considered:**
- K=32: Standard chess default, but too low for limited match volume
- K=128: Too volatile, single matches cause excessive swings
- Variable K-factor: Adds complexity; fixed K simpler for early tournaments

---

## Rating Persistence

**Decision:** Fresh calculation each run (no persistence)

**Rationale:**
- Simpler to implement and test in early iteration
- Easy to experiment with different K-factors or baseline ratings
- Deferred to later iteration when tournament data stabilizes
- Each run treats all API-fetched matches as ground truth

**Future iterations may add:**
- Persistent rating files (JSON) between runs
- Cumulative multi-tournament ratings
- Rating history snapshots

---

## Player Identity

**Decision:** Calculate/store with `user_id`, display with `slug` (fallback to `display_name` if slug is null)

**Rationale:**
- `user_id` is permanent and unique per player; avoids rating orphaning if name changes
- `slug` is stable and human-readable for output; rare edge case of release/reclaim
- `display_name` can change anytime, breaking rating continuity
- Approach matches Per-Ankh's own player tracking (see CLAUDE.md on profile slugs)
- Handles name changes gracefully: same player, same rating, just different display

**Alternatives considered:**
- `slug` alone: More readable but rare edge case of slug release
- `display_name` alone: Too volatile; loses rating history on name change

**CLI lookup (2026-08-17):** The `player` command now accepts the slug directly (matching what the leaderboard displays), falling back to `display_name` for slug-less players and to raw `user_id` for backward compatibility. Safe because `users.slug` is unique per account at the DB level; the `display_name` fallback isn't unique, so the calculator lists candidate `user_id`s if it matches more than one player.

---

## Rating Scope

**Decision:** 2026 Community Tournament only (first iteration)

**Rationale:**
- Simplifies MVP; focused baseline for testing ELO calculations
- Need to understand how multiplayer duels/other tournaments are indexed on site
- Clear, bounded dataset for validation

**Future iterations (scope expansion):**
- Include all tournaments (iterate through tournament list API)
- Include multiplayer games (scope: rating system design for user-submitted games)
- Separate or blended multi-tournament ratings
- Per-tournament ratings vs. cumulative global ratings

**Notes for future work:**
- Multiplayer games require investigation: are they indexed per-tournament or globally?
- How should 1v1 matches vs multiplayer FFA games be weighted in ELO?

---

## Division Handling

**Decision:** Equal weight for all matches (no per-division pools or modifiers)

**Rationale:**
- 2026 tournament has only Swiss-phase matches (no elimination yet)
- No separate rating pools between Division A and B
- All matches treated equally for ELO calculation

**Future iterations (match-type weighting):**
- Planned three-tier weighting: user-submitted < swiss tournament < elimination tournament
- Requires: understanding how user-submitted multiplayer games are indexed; whether to include them; how to handle 3+ player FFA games
- Stub: add `match_type` parameter to ELO calculator; set all current matches to `swiss`; implement weighting formula when scope expands
- Example future weights: user-submitted K=32, swiss K=64, elimination K=80

**Not planned:**
- Separate rating pools per division (A vs B)
- Division-based point bonuses/maluses

---

## Output Format

**Decision:** Multiple command modes (CLI-selectable)

**Primary outputs (MVP):**
1. **Leaderboard:** Players sorted by final ELO with match count, win/loss record
2. **Single match report:** Show both players, their ELO before/after, K-factor applied, result
3. **Single player report:** Show player's match history with ELO progression through tournament

**Nice-to-have exports:**
- CSV: Leaderboard or per-match data
- JSON: Raw ratings + match history for visualization tools

**Implementation approach:**
- Script accepts command-line subcommand: `elo leaderboard`, `elo match <match_id>`, `elo player <user_id>`
- All modes calculate fresh ratings per run from API data
- Display includes: player slug, current rating, matches played, wins/losses, rating change from tournament start

---

## References & External Resources

### Canonical ELO References
- **Arpad Elo's original work** — Mathematical foundation of the rating system (academic baseline)
- **Lichess Rating System** — Modern, well-documented ELO implementation for online chess; uses K=32 default, variable by game type
- **Chess.com Ratings** — Competitive ELO precedent; clear K-factor documentation
- **Glicko-2** — Bayesian extension to ELO accounting for rating volatility over time (advanced alternative; not adopted here)

### Community/Sports Applications
- **Tennis Abstract** (https://www.tennisabstract.com/)
  - **Insights for Per-Ankh:** Uses Elo ratings for professional tennis; baseline around 2000 (vs our 1500). Worth noting: their higher baseline reflects wider skill variance in professional sports. Our 1500 is appropriate for a smaller community tournament.
  - **K-factor:** Not explicitly documented on site, but professional sports typically use lower K (32-40) for stability; our K=64 is aggressive by comparison, which is correct for early/limited matches.
  - **Division handling:** No separate pools; all matches treated equally across surfaces/tournaments. Aligns with our decision.

- **"How We're Forecasting The 2016 U.S. Open" (FiveThirtyEight)** — [Article no longer available]
  - **Noted for reference:** FiveThirtyEight's Elo application to tournament sports emphasizes recency weighting and match-type adjustments. Our future match-type weighting (user < swiss < elimination) follows this precedent.

- **"A Stumbling Block for Elo" (David Aldous, UC Berkeley)** — https://www.stat.berkeley.edu/~aldous/Papers/me-Elo-SS.pdf
  - **Academic perspective on Elo limitations:** Discusses convergence speed, player pool size effects, and when Elo breaks down
  - **Relevant to Per-Ankh:** Small player pool (~50-78 players) means ratings may not fully converge. His analysis supports our K=64 (faster convergence needed) and fresh-calculation approach (easier to restart/adjust if needed).

### Assessment Against Our Decisions

| Decision | Tennis Abstract | Lichess | Berkeley Paper | Per-Ankh Choice | Notes |
|----------|-----------------|---------|-----------------|---|---|
| Baseline | 2000+ | 1500+ | Flexible | **1500** | ✓ Symmetric, matches Lichess precedent for new systems |
| K-factor | ~32-40 | 32 default | Varies | **64** | ✓ Higher is correct for limited match volume; professional sports use lower K due to match frequency |
| Persistence | Historical (years) | Per-session | Not discussed | **Fresh per run** | ✓ Appropriate for early iteration; persistence can be added later |
| Division/Surface | No pools | No pools | Not discussed | **No pools** | ✓ Aligns with established precedent |
| Match-type weighting | Implicit (tournament tier) | Not visible | Discussed as important | **Planned (stubbed)** | ✓ Our three-tier approach (user < swiss < elimination) follows FiveThirtyEight thinking |

---

## Historical Record

- **2026-08-17:** `player` command now takes slug (leaderboard-friendly) instead of requiring `user_id`, with fallback to `display_name`/`user_id` for edge cases.
- **2026-08-16:** Output format set to multiple command modes: leaderboard (primary), single-match report (primary), single-player report (primary), with CSV/JSON as nice-to-haves (discussion with project lead).
- **2026-08-16:** Division handling set to equal weight (no per-division pools), with future match-type weighting (user-submitted < swiss < elimination) stubbed in code (discussion with project lead).
- **2026-08-16:** Rating scope set to 2026 Community Tournament only, with future expansion to all tournaments and multiplayer games (discussion with project lead).
- **2026-08-16:** Player identity set to user_id for calculation, slug for display (discussion with project lead).
- **2026-08-16:** Rating persistence set to fresh-calculation-per-run (discussion with project lead).
- **2026-08-16:** K-factor set to 64 (discussion with project lead).
- **2026-08-16:** Baseline rating set to 1500 (discussion with project lead).
