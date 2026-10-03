# AX Branch — PROJECT_STATE (development)

Updated 2026-10-03 · version **0.1.2** · repo `AX-Branch/ax-branch` (local git only, not pushed).
Runtime project state is in `../workspace/axbranch.sqlite3` and each `HANDOFF.md`; this file
covers the *development* of AX Branch itself.

## Working now (verified)
- Goal -> CEO plan -> dynamic pipeline -> temporary agents -> artifact -> independent verification
  -> FAIL rebuild -> PASS -> CEO report. Proven live on project `P-20261003-906ead`.
- SQLite runtime state, enforced lifecycle, PAUSED/resume from DB (proven live after a provider timeout).
- Claude Code CLI and Codex CLI both executed real turns (Claude: CEO + builder; Codex: engineer + verifier).
- Deterministic gate (compile + self-test) overrides model verdicts; artifacts hashed and versioned.
- Owner close flow (save / pause / discard+confirm) and verified Obsidian archive — unit-tested; not yet used live.
- Windows exe builds and launches (`dist/AXBranch/AXBranch.exe`).

## Provider status (honest)
| Capability | Claude Code | Codex CLI |
|---|---|---|
| Runs an agent turn (any role) | live-proven | live-proven (engineer, verifier) |
| Quota failover to the other | unit-tested only | unit-tested only |
| Drives a project as the session (`python -m axbranch run`) | live-proven | **live-proven** (2026-10-03, see `evidence/`) |

## Live projects (both PENDING_CLOSE, Owner decision; do not close without the Owner)
- `P-20261003-906ead` — business-registration-number validator (v2 PASS). Owner: keep open for now.
- `P-20261003-06983b` — won amount → Hangul (v1 PASS); finished by a Codex CLI session (continuation test).

## Next
See `TASK_STATE.md`.
