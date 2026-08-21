# ELO Calculator Design Decisions

This document captures design decisions for the tournament ELO rating calculator built into the match fetching scripts.

## Why a Rating System?

Prediction — FiveThirtyEight's actual goal in the Elo research cited below — is not why this exists, and we haven't built it (no forecasting or win-probability feature; ratings here are purely retrospective). **The real goal is the same one USGA built the World Handicap System for: to build and sustain a community, not to forecast it** (discussion with contributor, 2026-08-19).

USGA is explicit about this. A handicap exists so a beginner and a scratch golfer can play a *meaningful* match against each other (via net scoring), and so newer or less-skilled players have a legible way to see themselves improve and stay motivated to keep playing — not primarily to predict who scores lowest. Matching people of comparable ability, and making improvement visible, is the point; forecasting is something other systems have layered on top of the same underlying math (see FiveThirtyEight below), not the reason the math exists.

That's the actual goal here too:
- **A visible, responsive rating gives every player a sense of standing and progress** — including players who'll never top the leaderboard. A newcomer's rating climbing after a string of close losses is a legible improvement signal on its own, without needing a single win.
- **It sets up matchmaking, not just ranking.** Pairing players of comparable skill — the actual USGA-style use case — isn't a built feature yet; Swiss pairing already approximates it by record, but a rating could do it earlier and more precisely, before results diverge.
- **An upset stays legible and worth celebrating.** A low-rated player beating a high-rated one produces a large, visible rating swing specifically because the system is built to notice it — that's a participation signal (this game mattered), not a forecasting one.
- **Encouraging participation matters more than ranking precision.** A rating system that makes new and returning players feel seen is doing its job even if it's a worse predictor than a system tuned purely for forecast accuracy would be.

The responsive, transparent design already documented below — a fixed, aggressive K=64, full match history, no hidden model — fits this goal well, even though it wasn't originally framed this way. If prediction/forecasting is ever wanted later (pre-match win probabilities, tournament-outcome forecasts), that's a genuinely separate feature layered on top of this rating — the way FiveThirtyEight layered it on top of Elo for tennis — not a reason to redesign the rating itself.

---

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
- "How should 1v1 vs. multiplayer be handled" is reframed, not resolved, as of 2026-08-19 — see Division Handling below. It's an architecture fork (pairwise math doesn't apply to 3+ players), not a weighting question.

---

## User-Submitted Games as a Data Source — Blocked (2026-08-19)

**Goal, as scoped (discussion with contributor):** pull non-tournament, user-submitted 1v1 human-vs-human games from the Per-Ankh API as an additional ELO data source, gated behind an opt-in flag (this would move ratings significantly, hence opt-in rather than default-on). Already decided: weight these identically to tournament matches — no special K-factor, consistent with retiring match-type weighting (see Division Handling below) — and exclude AI opponents and non-1v1 games entirely (excluded, not weighted differently).

**Researched and found blocked, not just unbuilt.** Tournament matches and casual uploads resolve player identity at fundamentally different points in the data model:

- **Tournaments identify both players at the *match* level, before a game is ever played.** A tournament match's two sides come from `tournament_slots` — real accounts pre-registered into Slot A/Slot B at signup, independent of any save file. When a game is later reported for that match, the Worker stamps the *already-known* `slot_a_user_id`/`slot_b_user_id` onto the match row (`cloud/src/games.ts`). The save file is never the source of truth for who's playing — the registration is.
- **Self-reported/casual uploads have no equivalent match-level entity.** There's just a `game` — a parsed save tied to exactly one known account, the uploader. Every other seat in `player_roster` is save-file-native (`player_name` — the in-game leader/character name, not a Per-Ankh account; `nation`; `is_human`) with **zero account linkage exposed anywhere in the public API.** `GET /v1/games/:id` injects only the uploader's own resolved identity (`user_id`, `slug`, `display_name`) — confirmed by reading `cloud/src/games.ts`'s game-detail handler directly.
- The one place real identity *does* exist for other seats is `online_id` (Steam/GOG/Epic ID), matched against the private `user_online_ids` table — session-gated to each user reading it about *themselves*, and deliberately stripped from every non-owner view. That's an existing, intentional PII boundary (`cloud/src/CLAUDE.md`'s "online_id never leaves its lane"), not an oversight. Working around it isn't the right move even where it might be technically possible from a script's vantage point.

**Confirmed empirically, 2026-08-19, against a real 1v1 save file (not just inferred from the schema):** both human seats carried a distinct, populated Steam64 `OnlineID` attribute in the raw save XML — the non-uploading opponent's seat included, not just the uploader's. So this is **not** a save-file/game-data gap; Old World's format already embeds a stable per-seat platform ID for every human player, and Per-Ankh's own parser already has a schema field for it (`player_roster[].online_id`). The gap is entirely that the API never resolves or returns it for any seat but the uploader's.

**Net effect:** for a 2-human casual game, we can know who uploaded it and whether they won — but not who they played against. Pairwise ELO needs both sides' identity, and only one is ever available today.

**What would actually unblock this — a specific, now-verified ask, not just "expose more data":** resolve `online_id → user_id` **server-side**, and expose only the *resolved* `user_id` per `player_roster` seat — never the raw `online_id` itself. This is the same resolve-and-inject pattern the API already uses for the uploader's own seat (`user_id` is injected today; `online_id` itself is never returned to non-owners) — extending it to every human seat, not just the uploader's, closes this gap without moving the existing PII boundary at all. The empirical check above confirms the raw ingredient this needs is already present for both seats, not just the uploader's — this isn't speculative.

A lighter, opt-in alternative that wouldn't need any `online_id` handling change: let the uploader tag other seats with known Per-Ankh accounts post-upload, unverified — closer to how the `prospector.fly.dev` historical import required a human who knew the players (see Player Identity above), just smaller-scale and ongoing rather than a one-time bulk import.

**Secondary consideration for whenever this unblocks:** `GET /v1/games/:id` costs `anon_read` budget — 200/hr **per IP**, not per session or per script — for every caller except the actual game owner. Bulk-fetching many users' game details at scale needs real throttling design, not just a fetch loop.

This directly affects two items in `elo-calculator-usage.md`'s Planned list — the human/AI eligibility filter and the 2-player/3+-player architecture fork — both scoped assuming "if user-submitted games ever become a data source" was purely a build question. It's now known to also be an identity-resolution question outside this project's control.

---

## Match Deduplication via `xml_game_id` — Verified Feasible (2026-08-19)

**The question:** if two different participants each upload their own save from the *same* game, can we detect that and reconcile rather than double-counting? Directly relevant to `elo-calculator-usage.md`'s "Match dedup/conflict rule across sources" Planned item.

**Verified, not just found in the schema:** every save's XML root carries a `GameId` attribute — confirmed directly against a real save file, where it read as a standard UUID (`8a378aa9-cfd6-4ce6-b18e-3709c9043d27`) sitting alongside other *session-level* settings (`MapClass`, `MapSize`, `MapAspectRatio`, engine `Version`), not anything player- or upload-specific. Per-Ankh's parser already extracts this into `xml_game_id` (`src/lib/parser/parsers/match-metadata.ts`, from `root["@_GameId"]`), and it's stored on every `games` row (`NOT NULL` column, `cloud/migrations/0002_cloud_schema.sql`).

**Unlike the opponent-identity gap above, this isn't blocked by a privacy boundary — it's a simpler omission.** `xml_game_id` isn't PII. It's just not currently exposed anywhere in the public API (`GET /v1/games` and `GET /v1/games/:id` both omit it) and not used server-side either — no index on the column, no dedup query against it anywhere. It's write-only today: stored, never read back.

**What would unblock this — also worth raising with the API developers, and lower-friction than the identity fix:** expose `xml_game_id` on the game list/detail responses (or a dedicated lookup). Any consumer could then detect "these two uploads are the same underlying game" directly by comparing the field, no server-side resolution logic or PII handling required — a plain equality check.

**Stability across turns: confirmed (2026-08-20).** Checked two saves of the same ongoing game (Turn 90 and Turn 98) — identical `GameId` on both. Checked a third, unrelated game (different match, sharing one player with the first) — a completely different `GameId`, confirming the identifier is per-game-session, not per-player. As a real-world bonus: this also settled a save the contributor was themselves unsure about (a differently-named file "probably" from the same game as the Turn 90/98 pair) — its `GameId` didn't match, so it's confirmed to be a different game, not a mislabeled save of the same one.

**Cross-participant match, the actual target scenario: confirmed (2026-08-20).** The checks above all used saves from a single uploader. This one is stronger: the contributor's own save of a game and their opponent's independently-uploaded save of *the same* game — two different people, two different files, no coordination beyond both having played the match — carry an **identical `GameId`**. This is the literal case the dedup question opened with ("if two players were to upload a save file from the same game, could we verify that"): yes, confirmed directly, not inferred from same-uploader data.

**Also verified: `xml_game_id` can never collide with Per-Ankh's own `game_id`.** `game_id` is a Per-Ankh-generated `nanoid(21)` (`cloud/src/games.ts`), assigned per upload; `xml_game_id` is parsed from the save's own `GameId` XML attribute, assigned per game session by Old World itself — different generator, different length (21 vs. 36 characters), different character format (nanoid alphabet vs. UUID). Confirmed both by code inspection and by an empirical test request showing the two values side by side.

---

## Division Handling

**Decision:** Equal weight for all matches (no per-division pools or modifiers)

**Rationale:**
- 2026 tournament has only Swiss-phase matches (no elimination yet)
- No separate rating pools between Division A and B
- All matches treated equally for ELO calculation

**Retired 2026-08-19: match-type importance weighting.** The original plan was a three-tier K-factor weighting (user-submitted < swiss < elimination), stubbed but never implemented. Backed out after independent evidence from two unrelated domains argued against it (discussion with contributor):
- FiveThirtyEight tested importance-weighting Grand Slam vs. regular-tour tennis results and found it *hurt* prediction accuracy — see References & External Resources below.
- USGA's World Handicap System explicitly does **not** weight competition scores differently from casual rounds in the handicap math itself; a "Competition" score tag exists only to support later analysis, not to change how much a given score moves the rating.
- Both land on the same principle: don't presume a context-based weight helps without evidence it does. Tag provenance if it's useful for later analysis; don't build a weighting formula on the assumption that tournament results are inherently "worth more."

**What actually needs handling instead — two distinct axes, correctly separated (neither is a weight):**

1. **Eligibility: human vs. AI opponents.** A filter, not a weight — closer to WHS's peer-review eligibility gate (a score only counts if it's verifiably a real result) than to importance-weighting. Only human-vs-human results are rateable at all. Maps directly onto the app's existing `scope` classification (`cloud/src/games-scope.ts`): `vs_ai` games (exactly one human) must never enter the calculator; `mp` games (2+ humans) are the eligible pool. No new schema needed if/when this becomes a live data source — the field already exists and already distinguishes exactly this.
2. **Architecture fork: 2-player vs. 3+ player pools.** A different algorithm, not a weight. `calculate_elo_delta()` and the whole canonical-match schema are strictly pairwise, and that's correct as-is for tournament matches, which are always exactly 2 players by construction — a Swiss/Championship "match" *is* slot_a vs. slot_b; no 3+ case exists in tournament data. This only becomes live if user-submitted multiplayer games are ever added as a source: a 3+ player FFA result can't be fed through the same pairwise formula unmodified. It needs either a genuinely different algorithm (e.g., decomposing an FFA into pairwise sub-results, or a placement-based system like TrueSkill) or explicit exclusion from rating — not a K-factor bolted onto the current pairwise math.

**Not planned:**
- Separate rating pools per division (A vs B)
- Division-based point bonuses/maluses
- Any K-factor weighting keyed to tournament phase or match "importance"

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
  - **Reviewed 2026-08-19 against a saved copy of the archived page** (contributor retrieved it; see Historical Record). Corrects a mischaracterization this doc previously carried — the article was cited here as supporting match-type/recency weighting; it actually argues against that, on their own tested data.
  - **Baseline:** confirms 1500 as an arbitrary-but-symmetric start for unrated players — matches our decision directly, not just by analogy.
  - **K-factor:** they explicitly reject a flat/fixed K ("the crudest thing to do") for `K / (matches_played + offset)^shape`, fit to K=250, offset=5, shape=0.4 — a K that *shrinks as a player accumulates matches* (experience-based, not calendar-time-based — "recency weighting" was the wrong word for this). Effective K comes out to roughly 130 for a brand-new player and roughly 45 for one with ~50 matches. Our fixed K=64 sits inside that range for a typical Swiss-tournament participant's match count, but doesn't adapt with experience the way theirs does.
  - **Match-type/importance weighting: they tested it and rejected it.** They tried weighting Grand Slam (best-of-5) results more heavily than regular tour matches and found predictions got *slightly less accurate*, so they didn't adopt it; they also tested set/game-level granularity (margin-of-victory-style) and found that unhelpful too. Part of the evidence behind retiring our own match-type weighting plan entirely — see Division Handling above.
  - **What they did validate:** blending two separate Elo tracks — a player's overall rating and a surface-specific (hard-court) rating — for event-specific starting ratings, weighted 0.71 overall + 0.29 surface. No direct Old World analogue is planned, but a similar overall/context-specific blend (e.g., by nation or map type) is a more evidence-backed direction than importance-weighting, if this is ever revisited.

- **USGA World Handicap System** — https://www.usga.org/content/usga/home-page/handicapping/world-handicap-system/topics.html (researched 2026-08-19, live web, not archived — see Historical Record)
  - **Not Elo — a different rating system (Score Differential: `(113/Slope) × (Adjusted Gross Score − Course Rating − PCC)`), but directly relevant to the match-type weighting question** because it's a mature, widely-used system that had to make the same call we're making.
  - **Tournament ("Competition") scores are not weighted differently in the math.** Per USGA's own FAQ, a "C"-designated competition score "is not used any differently for the purposes of calculating a Handicap Index" — same formula, same weight as any casual round. The tag exists only so a committee can *later analyze* whether players perform differently in competition vs. casual play — not to alter the calculation per-score.
  - **What actually varies is eligibility, not weight** — a binary gate: every acceptable score, tournament or casual, requires peer review (played in the presence of a verifying person, posted promptly). No verification, no counting, regardless of context. A per-competition Committee can manually override a specific player's Playing Handicap if there's evidence it doesn't reflect demonstrated ability — a judgment call for one event, not an automated formula.
  - **Relevant to Per-Ankh:** independent second source (unrelated domain, unrelated methodology) landing on the same principle as the FiveThirtyEight review above — tag match provenance for analysis if useful, don't build a weighting scheme on the assumption that competitive context inherently changes how much a result should count.

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
| Match-type weighting | Implicit (tournament tier) | Not visible | Discussed as important | **Retired 2026-08-19** | ✓ Backed out — FiveThirtyEight tested it and found it hurt accuracy; USGA's WHS deliberately doesn't do it either. Replaced by two real axes (human/AI eligibility; 2-player vs. 3+ player architecture), neither a weight — see Division Handling above. |

---

## Historical Record

- **2026-08-20:** Confirmed the actual target scenario directly: the contributor's own save and their opponent's independently-uploaded save of the same game carry an identical `GameId`. Everything checked previously used saves from a single uploader (same-person, different turns/games); this is the first cross-participant confirmation — two different people, two different files, matching identifier. Also confirmed `xml_game_id` can never coincide with Per-Ankh's own `game_id` (different generator, length, and format), by code inspection and an empirical test request.
- **2026-08-20:** Confirmed `GameId` stability across turns of the same game, using two more save files the contributor provided (Turn 90 and Turn 98 of the same match: identical `GameId`; a third, unrelated match sharing one player: different `GameId`). Upgrades the "Match Deduplication via `xml_game_id`" section from partially-inferred to fully verified. As a real-world side effect, also resolved a save the contributor was themselves unsure about — confirmed to be a different game than they thought, by `GameId` mismatch.
- **2026-08-19:** Verified match-dedup is feasible via `xml_game_id` — every save's XML root carries a `GameId` UUID at the session level (confirmed against the same real save file used for the identity check below), already parsed and stored on every `games` row, just never exposed via the public API or used for dedup server-side. Unlike the opponent-identity gap, not privacy-blocked — a plain omission, simpler to raise with the API developers. Directly resolves the open question in `elo-calculator-usage.md`'s "Match dedup/conflict rule across sources" Planned item.
- **2026-08-19:** Empirically verified the user-submitted-games blocker (below) against a real 1v1 save file the contributor provided, rather than leaving it inferred from the parser schema alone. Both human seats had a distinct, populated Steam64 `OnlineID` in the raw save XML — confirms the gap is entirely a Per-Ankh API/policy choice, not missing save-file data. (Steam IDs and the real players' names aren't recorded here — this repo is public.)
- **2026-08-19:** Researched pulling user-submitted (non-tournament) games as an ELO data source — the natural next step after retiring match-type weighting, since we'd already decided to weight them identically to tournament matches and exclude AI/non-1v1 games. Found genuinely blocked, not just unbuilt: the public API never resolves a casual game's non-uploader players to Per-Ankh accounts (confirmed by reading `cloud/src/games.ts`'s game-detail handler directly), unlike tournament matches, which identify both sides at the match-registration level before a game is even played. Documented as its own section with a specific, privacy-respecting proposed fix (contributor intends to raise it with the API developers), rather than folded into the Planned list where it would misleadingly read as just an implementation task.
- **2026-08-19:** Added a "Why a Rating System?" section up front — the doc previously jumped straight into parameter-level decisions (baseline, K-factor, ...) without ever stating the actual goal. Established (discussion with contributor): the point is building/sustaining a community and enabling future matchmaking, modeled on USGA's stated purpose for golf handicaps — not prediction, which is FiveThirtyEight's goal in the cited research and isn't a feature this project has built. Docs only; no behavior change, but this reframes the *reason* behind existing choices like the aggressive fixed K=64.
- **2026-08-19:** Retired the match-type importance-weighting plan (user-submitted < swiss < elimination K-factors), on the combined evidence of the FiveThirtyEight review below and new research into USGA's World Handicap System (which explicitly does not weight competition scores differently from casual ones in the handicap math). Replaced with two correctly-separated real distinctions, neither a weight: an eligibility filter for human-vs-AI composition (maps onto the app's existing `scope: vs_ai/mp` classification) and an architecture fork for 2-player vs. 3+ player pools (pairwise Elo doesn't apply to FFA without a different algorithm). See Division Handling (discussion with contributor).
- **2026-08-19:** Reviewed the FiveThirtyEight "2016 U.S. Open" reference against a saved archive copy (contributor retrieved it from the Wayback Machine, since the live article is gone and automated fetching of web.archive.org isn't available). Corrected this doc's characterization of it: it does not support match-type/recency weighting the way the References section and Assessment table previously claimed — the article's own tested finding is that importance-weighting (Grand Slam vs. regular tour) *hurt* prediction accuracy, so FiveThirtyEight deliberately didn't adopt it. What it does validate: our 1500 baseline, and (as a new data point) a surface-specific/overall Elo blend that has no current Per-Ankh analogue. No behavior changes from this review — documentation accuracy only.
- **2026-08-18:** Extended test coverage to the other two scripts: `test_fetch_tournament_matches.py` (14 tests -- extracted `filter_matches()` out of `main()` first so the phase/division/status filtering is unit-testable; also a regression test for the nation/map `None`-vs-missing-key crash fixed the same day the script was converted to argparse) and `test_per_ankh_api.py` (8 tests, `unittest.mock.patch` on `urlopen` -- no network calls -- scoped to URL construction and the `None`-vs-`[]` distinction in `fetch_tournament_matches()`, which the two calling scripts treat differently). Same verification standard as below: every regression test confirmed to actually fail when its named bug is reintroduced.
- **2026-08-18:** Added `scripts/test_elo_calculator.py` (stdlib `unittest`, no new dependency) — 26 tests covering `calculate_ratings()`, `load_source_file()` validation, `find_player()`, `preferred_name()`/`transliterate()`, and the `export snapshot` round-trip. Every regression test in it was verified to actually catch the bug it names: reintroduced each historical bug's effect into the current code via monkey-patching and confirmed the corresponding test fails, then confirmed it passes again against the real fixed code — not just "written to pass," actually load-bearing.
- **2026-08-18:** Fixed a latent order-dependence bug in `calculate_ratings()`: matches sharing an exact `date` string were replayed sequentially in whatever order they appeared in the loaded list/file, so a player with two same-date matches got a different final rating depending on that arbitrary order (confirmed with a synthetic reproduction: 1497.06 vs 1502.94 for the identical two matches, order swapped). Matches now batch by exact-date match against pre-batch ratings, order-independent. Verified as a no-op for currently-loaded data (byte-identical leaderboard/player-history output before and after) since no source has a player playing twice on the same date — checked programmatically across all of `scripts/data/`, and confirmed directly against `prospector.fly.dev` that no finer-than-day timestamp is available anywhere on that site to recover true order instead.
- **2026-08-18:** Rating scope superseded: multi-source chronological replay (`--source`, repeatable; `--no-live`; `export snapshot`) replaces the single-tournament-only decision. Synthetic-player convention added for historical opponents with no Per-Ankh account (discussion with contributor).
- **2026-08-18:** Imported 52 historical matches / 33 players from `prospector.fly.dev` (third-party, non-Per-Ankh Old World tournament visualizer) as `scripts/data/prospector-2025-tournament-matches.json`; 18 players hand-mapped to real Per-Ankh accounts, 15 with no account marked synthetic (discussion with contributor).
- **2026-08-17:** Fixed two pre-existing correctness bugs: `calculate_ratings()` was writing one shared, tautologically-mis-attributed match-history entry to both players (opponent always showed as the slot_b player; result always showed "W"); `print_match()` separately reconstructed pre-match ratings but silently dropped a player's prior matches played from the other slot.
- **2026-08-17:** `player` command now takes slug (leaderboard-friendly) instead of requiring `user_id`, with fallback to `display_name`/`user_id` for edge cases.
- **2026-08-16:** Output format set to multiple command modes: leaderboard (primary), single-match report (primary), single-player report (primary), with CSV/JSON as nice-to-haves (discussion with contributor).
- **2026-08-16:** Division handling set to equal weight (no per-division pools), with future match-type weighting (user-submitted < swiss < elimination) stubbed in code (discussion with contributor).
- **2026-08-16:** Rating scope set to 2026 Community Tournament only, with future expansion to all tournaments and multiplayer games (discussion with contributor).
- **2026-08-16:** Player identity set to user_id for calculation, slug for display (discussion with contributor).
- **2026-08-16:** Rating persistence set to fresh-calculation-per-run (discussion with contributor).
- **2026-08-16:** K-factor set to 64 (discussion with contributor).
- **2026-08-16:** Baseline rating set to 1500 (discussion with contributor).
