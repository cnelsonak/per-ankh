# ELO calculator historical match data

Historical match snapshots for `scripts/elo-calculator.py --source` — the
portable `players` + `matches` schema documented in
[`docs/elo-calculator-usage.md`](../../docs/elo-calculator-usage.md#historical-data--multiple-sources).

Everything in this directory except this README is gitignored. Fetched,
scraped, or otherwise externally-sourced data isn't tracked in this repo (same
reasoning as `backups/` and the `Reference` checkout — see root `.gitignore`)
— regenerate or re-obtain it locally instead.

## `prospector-2025-tournament-matches.json`

52 matches / 33 players imported from `prospector.fly.dev`, a third-party Old
World tournament visualizer covering the season before Per-Ankh's own 2026
Community Tournament. Not reproducible by re-running a script: that site has
no public API or stable player IDs, so the import required reverse-engineering
its internal Dash callback protocol and hand-mapping player identity to real
Per-Ankh accounts (judgment calls on which differently-spelled names were the
same person) — done manually with the tournament organizer, not automated.
See `docs/elo-calculator-design.md` § Player Identity → Synthetic players for
the full process and rationale.

If you need this file, ask the tournament organizer for a copy rather than
re-scraping — the manual identity-mapping step won't reproduce identically.
