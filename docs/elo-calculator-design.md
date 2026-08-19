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
- Rating history snapshots

**Still true after 2026-08-18's multi-source support (see [Rating Scope](#rating-scope)):** `export snapshot` persists raw *match data* so it doesn't need re-fetching, not computed *ratings* — every run still replays every loaded match from `BASELINE_ELO` and recomputes ratings fresh. Cumulative multi-tournament ratings are now done, but via chronological replay over more input matches, not via carrying rating state between runs.

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

### Synthetic players (2026-08-18)

Historical sources can include players with no Per-Ankh account — e.g. someone from an earlier, unaffiliated tournament (`prospector.fly.dev`) who never signed up here. They get a `source: "synthetic"` player entry with a fabricated identity: `user_id` prefixed `prospector:`, `slug` prefixed `prospector-` (both just internal namespacing so they can't collide with a real account, never meant to be shown), and a real `display_name`.

**Decision:** synthetic players' matches fully participate in rating calculation — they produce real ELO deltas for the real players who beat/lost to them, exactly like any other match — but they're **excluded from the leaderboard and `export json`/`export csv`**, since they haven't opted into being ranked on the current system.

**Rationale:**
- Dropping their matches entirely would understate real players' results (a win over anyone, present or historical, is still a win) and would silently break chronological replay (some real players' *earliest* results are matches against synthetic opponents).
- Displaying them alongside real accounts would misrepresent people as being "on Per-Ankh" who never signed up.
- `find_player`/`match` still resolve them (by `display_name`, not the internal `prospector-` slug) so a specific historical result stays auditable even though the person isn't ranked.

**Identity mapping process:** for the `prospector.fly.dev` import specifically, the site had no stable player IDs — everything was inferred from free-text save-file titles. A `match-breadcrumb` Dash callback turned out to give clean, authoritative `"Player (Nation) vs Player (Nation)"` text per match (sourced from the actual save data, unlike the noisy upload title), which resolved player pairing and the winner 100% reliably. Mapping those names to real Per-Ankh accounts, and judging which differently-spelled names were the same person (e.g. `Ninja`/`ninja`/`Ninjaa`), was **not automatable** — done by the tournament organizer, who knows the players, via `/u/<slug>` lookups. 15 of 33 distinct players from that import had no Per-Ankh account and became synthetic.

---

## Rating Scope

**Original decision (2026-08-16):** 2026 Community Tournament only (first iteration)

**Superseded 2026-08-18:** The calculator now replays the live tournament plus zero or more historical match files (`--source`, repeatable), merged into **one continuous chronological pass** — not separate per-tournament tallies. A player's rating reflects every loaded match in date order, regardless of which source it came from. See `elo-calculator-usage.md` § [Historical data & multiple sources](elo-calculator-usage.md#historical-data--multiple-sources).

**Rationale for combining rather than keeping per-tournament pools:**
- A continuous history is what ELO is for — an isolated per-tournament rating throws away exactly the signal ("this player already has a track record") that makes ratings meaningful across events.
- Keeps the single-tournament case as a trivial special case (one source, nothing to combine) rather than a separate code path.

**How scope expansion actually happened (not as originally planned):** the trigger wasn't "iterate through the tournament list API" — it was a **third-party, non-Per-Ankh site** (`prospector.fly.dev`, an independently-run Old World match visualizer) hosting last season's results. That data has no Per-Ankh `user_id`s at all; identity had to be hand-mapped from the site's free-text player names to real accounts by the tournament organizer (see [Player Identity](#player-identity) below). This means scope expansion is now **source-format-driven, not API-driven**: any match data — Per-Ankh's own API, a third-party site, a manually-curated file — can feed the calculator as long as it's expressed in the portable `players` + `matches` schema (documented in the usage doc). `export snapshot` produces that same schema from the live API, so the API path and the third-party-import path converge on one format instead of needing separate handling.

**Still true from the original decision:**
- Multiplayer/FFA games are still out of scope — the schema and the ELO update (`calculate_elo_delta`) are both strictly 1v1.
- "How should 1v1 vs multiplayer be weighted" is still an open question, now merged with the match-type weighting question below.

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
- **Before implementing:** read the FiveThirtyEight reference's corrected notes below (References & External Resources → "How We're Forecasting The 2016 U.S. Open") — their own tested data argues against this kind of importance-weighting, not for it. Doesn't block doing it (our axis is different), but go in aware, not assuming outside validation that doesn't actually exist.

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

- **"How We're Forecasting The 2016 U.S. Open"** (FiveThirtyEight; Benjamin Morris, Carl Bialik, Jay Boice; published 2016-08-28) — archived: https://web.archive.org/web/20170102161645/http://fivethirtyeight.com/features/how-were-forecasting-the-2016-us-open/
  - **Reviewed 2026-08-19 against a saved copy of the archived page** (project lead retrieved it; see Historical Record). Corrects a mischaracterization this doc previously carried — the article was cited here as supporting match-type/recency weighting; it actually argues against that, on their own tested data.
  - **Baseline:** confirms 1500 as an arbitrary-but-symmetric start for unrated players — matches our decision directly, not just by analogy.
  - **K-factor:** they explicitly reject a flat/fixed K ("the crudest thing to do") for `K / (matches_played + offset)^shape`, fit to K=250, offset=5, shape=0.4 — a K that *shrinks as a player accumulates matches* (experience-based, not calendar-time-based — "recency weighting" was the wrong word for this). Effective K comes out to roughly 130 for a brand-new player and roughly 45 for one with ~50 matches. Our fixed K=64 sits inside that range for a typical Swiss-tournament participant's match count, but doesn't adapt with experience the way theirs does.
  - **Match-type/importance weighting: they tested it and rejected it.** They tried weighting Grand Slam (best-of-5) results more heavily than regular tour matches and found predictions got *slightly less accurate*, so they didn't adopt it; they also tested set/game-level granularity (margin-of-victory-style) and found that unhelpful too. This is evidence against, not for, the currently-stubbed "user-submitted < swiss < elimination" weighting (see Division Handling above) — doesn't mean don't do it (their importance axis is Slam-vs-regular-tour, ours would be casual-vs-competitive, a different comparison), but this citation shouldn't be treated as precedent for it anymore.
  - **What they did validate:** blending two separate Elo tracks — a player's overall rating and a surface-specific (hard-court) rating — for event-specific starting ratings, weighted 0.71 overall + 0.29 surface. No direct Old World analogue is planned, but a similar overall/context-specific blend (e.g., by nation or map type) is a more evidence-backed direction than importance-weighting, if this is ever revisited.

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
| Match-type weighting | Implicit (tournament tier) | Not visible | Discussed as important | **Planned (stubbed)** | ⚠ FiveThirtyEight tested importance-weighting (Slam vs. regular tour) and found it *hurt* accuracy, so they dropped it — not the precedent this row previously claimed. Still plausible for us since our axis differs (casual vs. competitive, not just match "importance"), but goes in unvalidated, not FiveThirtyEight-backed. |

---

## Historical Record

- **2026-08-19:** Reviewed the FiveThirtyEight "2016 U.S. Open" reference against a saved archive copy (project lead retrieved it from the Wayback Machine, since the live article is gone and automated fetching of web.archive.org isn't available). Corrected this doc's characterization of it: it does not support match-type/recency weighting the way the References section and Assessment table previously claimed — the article's own tested finding is that importance-weighting (Grand Slam vs. regular tour) *hurt* prediction accuracy, so FiveThirtyEight deliberately didn't adopt it. What it does validate: our 1500 baseline, and (as a new data point) a surface-specific/overall Elo blend that has no current Per-Ankh analogue. No behavior changes from this review — documentation accuracy only.
- **2026-08-18:** Extended test coverage to the other two scripts: `test_fetch_tournament_matches.py` (14 tests -- extracted `filter_matches()` out of `main()` first so the phase/division/status filtering is unit-testable; also a regression test for the nation/map `None`-vs-missing-key crash fixed the same day the script was converted to argparse) and `test_per_ankh_api.py` (8 tests, `unittest.mock.patch` on `urlopen` -- no network calls -- scoped to URL construction and the `None`-vs-`[]` distinction in `fetch_tournament_matches()`, which the two calling scripts treat differently). Same verification standard as below: every regression test confirmed to actually fail when its named bug is reintroduced.
- **2026-08-18:** Added `scripts/test_elo_calculator.py` (stdlib `unittest`, no new dependency) — 26 tests covering `calculate_ratings()`, `load_source_file()` validation, `find_player()`, `preferred_name()`/`transliterate()`, and the `export snapshot` round-trip. Every regression test in it was verified to actually catch the bug it names: reintroduced each historical bug's effect into the current code via monkey-patching and confirmed the corresponding test fails, then confirmed it passes again against the real fixed code — not just "written to pass," actually load-bearing.
- **2026-08-18:** Fixed a latent order-dependence bug in `calculate_ratings()`: matches sharing an exact `date` string were replayed sequentially in whatever order they appeared in the loaded list/file, so a player with two same-date matches got a different final rating depending on that arbitrary order (confirmed with a synthetic reproduction: 1497.06 vs 1502.94 for the identical two matches, order swapped). Matches now batch by exact-date match against pre-batch ratings, order-independent. Verified as a no-op for currently-loaded data (byte-identical leaderboard/player-history output before and after) since no source has a player playing twice on the same date — checked programmatically across all of `scripts/data/`, and confirmed directly against `prospector.fly.dev` that no finer-than-day timestamp is available anywhere on that site to recover true order instead.
- **2026-08-18:** Rating scope superseded: multi-source chronological replay (`--source`, repeatable; `--no-live`; `export snapshot`) replaces the single-tournament-only decision. Synthetic-player convention added for historical opponents with no Per-Ankh account (discussion with project lead).
- **2026-08-18:** Imported 52 historical matches / 33 players from `prospector.fly.dev` (third-party, non-Per-Ankh Old World tournament visualizer) as `scripts/data/prospector-2025-tournament-matches.json`; 18 players hand-mapped to real Per-Ankh accounts, 15 with no account marked synthetic (discussion with project lead).
- **2026-08-17:** Fixed two pre-existing correctness bugs: `calculate_ratings()` was writing one shared, tautologically-mis-attributed match-history entry to both players (opponent always showed as the slot_b player; result always showed "W"); `print_match()` separately reconstructed pre-match ratings but silently dropped a player's prior matches played from the other slot.
- **2026-08-17:** `player` command now takes slug (leaderboard-friendly) instead of requiring `user_id`, with fallback to `display_name`/`user_id` for edge cases.
- **2026-08-16:** Output format set to multiple command modes: leaderboard (primary), single-match report (primary), single-player report (primary), with CSV/JSON as nice-to-haves (discussion with project lead).
- **2026-08-16:** Division handling set to equal weight (no per-division pools), with future match-type weighting (user-submitted < swiss < elimination) stubbed in code (discussion with project lead).
- **2026-08-16:** Rating scope set to 2026 Community Tournament only, with future expansion to all tournaments and multiplayer games (discussion with project lead).
- **2026-08-16:** Player identity set to user_id for calculation, slug for display (discussion with project lead).
- **2026-08-16:** Rating persistence set to fresh-calculation-per-run (discussion with project lead).
- **2026-08-16:** K-factor set to 64 (discussion with project lead).
- **2026-08-16:** Baseline rating set to 1500 (discussion with project lead).
