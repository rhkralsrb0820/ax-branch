# AX Branch — PROJECT_STATE (development)

Updated 2026-10-03 · version **0.1.1** · repo `AX-Branch/ax-branch` (local git only, not pushed).
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
| Drives a project as the session (`python -m axbranch run`) | done in this session | **not yet proven** |

## Live project
`P-20261003-906ead` is **PENDING_CLOSE**, waiting for the Owner to review and choose
SAVE & CLOSE / PAUSE / CLOSE WITHOUT SAVE (`python -m axbranch finish P-20261003-906ead`).

## Next
See `TASK_STATE.md`.
