# AX Branch — PROJECT_STATE (development)

Updated 2026-10-03 · version **0.1.6** · repo `AX-Branch/ax-branch` (local git only, not pushed).
Runtime project state is in `../workspace/axbranch.sqlite3` and each `HANDOFF.md`; this file
covers the *development* of AX Branch itself.

## Working now (verified)
- Goal -> CEO plan -> dynamic pipeline -> temporary agents -> artifact -> independent verification
  -> FAIL rebuild -> PASS -> CEO report. Proven live on project `P-20261003-906ead`.
- One session per project (OS run lock; GUI threads, CLI and Codex sessions cannot overlap).
- SQLite runtime state, enforced lifecycle, PAUSED/resume from DB (proven live after a provider timeout).
- Claude Code CLI and Codex CLI both executed real turns (Claude: CEO + builder; Codex: engineer + verifier).
- Deterministic gate (compile + self-test) overrides model verdicts; artifacts hashed and versioned.
- Generated code runs contained: clean env, Job Object caps, whole process tree killed (not file/network isolation).
- Owner close flow: SAVE & CLOSE live-proven (P-20261003-06983b); pause / discard+confirm unit-tested only.
- Windows exe: a goal ran end to end inside the packaged app (`--goal`), and a crashed run was resumed by the newer exe (`--resume`).
- Multi-file bundle artifacts (live-proven) alongside single markdown/python files.

## Provider status (honest)
| Capability | Claude Code | Codex CLI |
|---|---|---|
| Runs an agent turn (any role) | live-proven | live-proven (engineer, verifier) |
| Quota failover to the other | — | live: real Codex took over every Claude turn after a stand-in Claude refusal; genuine limit not yet seen |
| Drives a project as the session (`python -m axbranch run`) | live-proven | **live-proven** (2026-10-03, see `evidence/`) |

## Live projects (PENDING_CLOSE ones wait for the Owner)
- `P-20261003-906ead` — business-registration-number validator (v2 PASS). **PENDING_CLOSE — Owner: keep open; do not close.**
- `P-20261003-97494b` — venv guide (packaged-exe run, v2 PASS). PENDING_CLOSE.
- `P-20261003-4e3292` — textstats bundle (v2 PASS). PENDING_CLOSE.
- `P-20261003-46185d` — temperature converter, failover test (v4 PASS). PENDING_CLOSE.
- `P-20261003-06983b` — won amount → Hangul (v1 PASS); finished by a Codex CLI session; **CLOSED (SAVE)**, archived to `obsidian/AX-Branch-Vault/Branch_DB/Projects/`.

## Next
See `TASK_STATE.md`.
