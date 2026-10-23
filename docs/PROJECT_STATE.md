# AX Branch — PROJECT_STATE (development)

## Current development update — 2026-10-24 / 0.1.55 (forum demo)

Demo evidence: [forum demo](evidence/2026-10-24-forum-demo.md); full suite F155 394/394 on 0.1.55.
- Demo project P-20261023-2a0e75 is OWNER_REVIEW at v8 (verified). It serves the baseline: test team-routing 0.9669.
  LoRA was really trained (test team-routing 0.9159) and lost: lora_not_better, honestly recorded.
- The live GUI flow on a new goal (P-20261024-5bfdd1) passed end to end, including a real FAIL -> rework -> PASS.
- Owner launcher: demo-2026-11/AXBranch-Demo.cmd (source run; no fresh EXE).
- Not done: a packaged AX Branch EXE, the agent-table layout, the active-task feedback UX, and the permission label
  defect (tokenizer -> api_key). Production law-firm project and held reviews untouched.


## Current development update — 2026-10-20 / 0.1.46

Codex has taken over from Claude after its quota limit. Claude automatic continuation was cancelled;
the old Goal 3 worker tree was stopped before Codex continued the same saved project.
0.1.45 (7d2c381) and the preceding local releases are now on origin/main with Owner authorization.

- Goal 1 P-20261018-279325: OWNER_REVIEW, v3; reported verification 50/50 supported claims, no unmet criteria.
- Goal 2 P-20261019-52454a: OWNER_REVIEW, v2; independent CSV check agrees on 100 rows, 16 projects, 31 PASS, 69 FAIL.
- Goal 3 P-20261019-32a79d: PAUSED / HARNESS_BLOCKED, v1; consistency check passed. Native build and runtime
  checks succeeded, but verifier lacks packaging provenance and native network audit evidence.
- 0.1.46 supplies the build provenance (including reuse) to the verifier. It does not waive the native network gap.
  Native module: 7/7, including real EXE build. Full suite F146: 375/375 tests, 43 sequential audited batches; no skips, failures, unrun tests or surviving test processes.
- Existing production paused/review projects remain untouched. No Owner acceptance or closure is inferred.

Owner decision (2026-10-20): preserve the current evidence standard and HOLD Goal 3 until a native-network
observation tool is ready. Do not resume or waive the gap. 0.1.46 validation is complete; publish this verified fix with the Owner-authorized GitHub push.
Earlier sections below are historical snapshots.


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
