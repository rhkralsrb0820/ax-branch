# AX Branch — PROJECT_STATE (development)

## Current development update — 2026-10-19 / 0.1.41

Source delivery and one bounded evidence-context refinement are implemented. Claude reviewed them; B1/B2 are fixed.
Full suite 370/370 before the fixes; affected modules 71/71 after them.
Evidence: [source refinement](evidence/2026-10-19-source-refinement.md).
Goal 1 v2 is PAUSED / RateLimited after entering refinement, with no consistency problems. Research E2E has NOT passed.
Next: Claude-led Goal 1 re-verification, then Goal 2 (CSV) and Goal 3 (EXE).
Existing production Owner decisions remain untouched. Earlier sections are historical snapshots.


## Current development update — 2026-10-18 / 0.1.40

Source verification for cited research documents is implemented and regression-tested.
Full validation: 358/358, real EXE build enabled, 43 sequential audited batches, no test job survivors.
Evidence and limits: [source verification](evidence/2026-10-18-source-verification.md).
Next: approved Goal 1 v2 re-verification, then isolated CSV analysis and Windows EXE goals using Codex.
Existing production Owner decisions remain untouched. Earlier sections below are historical snapshots.


Updated 2026-10-17 · source version **0.1.37** · repo `AX-Branch/ax-branch` (private GitHub `rhkralsrb0820/ax-branch`).
Runtime project state is in `../workspace/axbranch.sqlite3` and each `HANDOFF.md`; this file
covers the *development* of AX Branch itself.

## Current development boundary (2026-10-17)

- Baseline main/origin 50138e5, clean; capability lifecycle, supported-evidence inventory and process-start
  cleanup/cancellation fixes implemented on a separate development branch. Live main execution is preserved.
- Source validation, scripted failure/replan and real-provider smoke results:
  [integration evidence](evidence/2026-10-17-capability-lifecycle.md).
- [Capability lifecycle](CAPABILITY_LIFECYCLE.md) defines what is enforced and what remains unsupported.
- The historical snapshot below is from 2026-10-10; its listed live-project states are not current status.
  Read SQLite/HANDOFF for current runtime state. The packaged EXE was not rebuilt in this development pass.

## Working now (verified)
- 0.1.32–0.1.33 (checkpoint before Test #3).
  - After a PASS, the CEO judges Goal satisfaction and may order its own bounded rework. REAL_PROJECT_VERIFIED in
    2 cases (incl. the Test #2 re-judgment: PARTLY → 1 autonomous rework → v6 PASS → DELIVER with classified gaps).
  - Generalization is UNPROVEN.
  - Re-plan knowledge retrieval: CODE_VERIFIED only.
- Goal -> CEO plan -> dynamic pipeline -> temporary agents -> artifact -> independent verification
  -> FAIL rebuild -> PASS -> CEO report. Proven live on project `P-20261003-906ead`.
- One session per project (OS run lock; GUI threads, CLI and Codex sessions cannot overlap).
- SQLite runtime state, enforced lifecycle, PAUSED/resume from DB (proven live after a provider timeout).
- Claude Code CLI and Codex CLI both executed real turns (Claude: CEO + builder; Codex: engineer + verifier).
- Deterministic gate (compile + self-test) overrides model verdicts; artifacts hashed and versioned.
- Owner review loop: verified deliveries go to OWNER_REVIEW; problems/changes reopen the same project (live-proven on P-20261003-bbad3c).
- Runtime Acceptance: artifacts must work when launched the way the Owner launches them (cli/web/gui), exact double-click included.
- Live activity visibility (agent, provider, CLI pid, elapsed, streamed output).
- Owner review = two questions (works? / what next?) with plain-language feedback; closure only on explicit finish.
- External connections of delivered programs need Owner approval (gate before build).
- Rendered-page checks (headless Edge), edit-based builds, sleep-aware timeouts, machine-wide provider slots, memory floor.
- Owner Effort KPI: `axbranch effort` (measured / estimated / unknown). Gap analysis: `GAP_ANALYSIS.md`.
- Archived knowledge is retrieved by later projects (live-proven, provenance in `context_used`).
- Upgrade Proposal path: gated by Owner satisfaction ≥ 90%; draft only.
- Generated code runs contained: clean env, Job Object caps, whole process tree killed (not file/network isolation).
- Owner close flow: SAVE & CLOSE live-proven (P-20261003-06983b); pause / discard+confirm unit-tested only.
- Windows exe: a goal ran end to end inside the packaged app (`--goal`), and a crashed run was resumed by the newer exe (`--resume`).
- Multi-file bundle artifacts (live-proven) alongside single markdown/python files.

## Provider status (honest)
| Capability | Claude Code | Codex CLI |
|---|---|---|
| Runs an agent turn (any role) | live-proven | live-proven (engineer, verifier) |
| Quota failover to the other | — | **genuine** Claude usage limit 2026-10-04: Codex took over every Claude turn automatically |
| Drives a project as the session (`python -m axbranch run`) | live-proven | **live-proven** (2026-10-03, see `evidence/`) |

## Live projects (OWNER_REVIEW / PENDING_CLOSE wait for the Owner)
- `P-20261003-bbad3c` — stock analyzer, improved per Owner feedback (v8 PASS: no CSV needed, beginner explanations, one-line interpretation with evidence/risks). **OWNER_REVIEW — Owner to test.**
- `P-20261003-906ead` — business-registration-number validator (v2 PASS). **PENDING_CLOSE — Owner: keep open; do not close.**
- `P-20261003-d356e8` — Hangul won → integer (packaged-exe run, reused 06983b knowledge, v2 PASS). PENDING_CLOSE.
- `P-20261003-97494b` — venv guide (packaged-exe run, v2 PASS). PENDING_CLOSE.
- `P-20261003-4e3292` — textstats bundle (v2 PASS). PENDING_CLOSE.
- `P-20261003-46185d` — temperature converter, failover test (v4 PASS). PENDING_CLOSE.
- `P-20261003-06983b` — won amount → Hangul (v1 PASS); finished by a Codex CLI session; **CLOSED (SAVE)**, archived to `obsidian/AX-Branch-Vault/Branch_DB/Projects/`.

## Next
See `TASK_STATE.md`.
