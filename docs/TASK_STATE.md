# AX Branch — TASK_STATE

| # | Task | Status |
|---|---|---|
| P0 | Audit repos, git state, reuse map | done (`AUDIT.md`) |
| P1 | Architecture + reuse map | done (`ARCHITECTURE.md`, `DECISIONS.md`) |
| P2–P4 | SQLite state, checkpoint/resume/handoff, Obsidian + GAI interfaces | done |
| P5–P7 | CEO / Verification boundaries, dynamic pipeline, Build→Verify→Rebuild | done |
| P8 | Provider abstraction + continuity | both CLIs run turns and drive sessions; failover live with a stand-in refusal; genuine limit not yet observed |
| P9 | Minimal Owner UI | done; automated widget e2e + live `--goal`/`--resume`; no recorded human click-through yet |
| P10 | Real end-to-end run | done (`P-20261003-906ead`, v1 FAIL → v2 PASS) |
| P11 | Windows exe | live goal run inside the packaged app; crash recovery by newer exe |

## Open, in priority order (see GAP_ANALYSIS.md)

### D-ART-1: built artifact versions are immutable (recorded 2026-10-08, Owner; implemented 0.1.17)
On 10-08 a failed rebuild overwrote `artifacts/v31/stock_analyzer.py`: the file was written before the DB
transaction, and the transaction then failed. v31 was restored from its recorded build output.
0.1.17:
- a version folder is claimed exclusively (`mkdir`, no reuse);
- an existing folder (a recorded version or a leftover) makes the build the next free version (event recorded);
- a failed commit deletes only the folder that build created;
- `check <id>` already verifies every version's sha256.
Not done: read-only file attributes on disk. Writes are refused in the engine, not by the OS.

### Backlog — D-SEC-1: OS-level network isolation for verification (separate security capability)
The audit-hook guard (0.1.16) refuses in-process network access only. Child processes, native code and the
Windows asyncio Proactor path are not covered. A real zero-egress guarantee needs an OS firewall rule or a
dedicated account, which is system setup and needs the Owner. Owner decision 2026-10-08: not part of the
v31 / project verification gate.

### Verification gate rule (Owner decision 2026-10-08, implemented 0.1.17)
PASS/FAIL uses only:
- the approved acceptance criteria (fixed at project start or by an Owner change);
- the deterministic checks.
A verifier finding that is not about an approved criterion (criterion = -1) is a **recommendation**: it is
recorded as a `verification_recommendations` event and never gates the version or becomes a requirement.
Every approved criterion must be judged by index.

### P0 — D-ORCH-1: rebuild loop and recovery misfires on P-20261003-bbad3c (recorded 2026-10-08, Owner)
After the Owner's v25 feedback the project ran v26→v31 with no product defect left after v27, then crashed
twice. Evidence: SQLite events/verifications, `workspace/logs/engine-errors.log`, Windows System log.
P-bbad3c is PAUSED (Owner stop, resume_state EXECUTING); the Stock Analyzer was not changed.
1. **Harness findings rebuilt the product.** v27/v29/v30 failed only on findings the verifier labelled
   HARNESS-UNVERIFIABLE, but every FAIL went REWORK→rebuild; v28 was a correct "retain unchanged" answer
   that the engine rejected as an empty deliverable (FAIL #23).
   Fix: findings carry `kind` product|harness|infra; only product findings rebuild. Harness-only → PAUSED
   `HARNESS_BLOCKED` (Owner/dev fixes the verifier), infra-only → `INFRA_FAILED` (auto re-verify);
   both keep the version and resume in VERIFYING.
2. **Repeat detection compared wording.** The same 4 findings in new words never matched.
   Fix: `engine.failure_code()` = finding kinds + failing deterministic step names (or the engine's
   rejection); a repeat after a forced change pauses with NEEDS_DECISION.
3. **Recovery re-planned a VERIFYING death and rebuilt into the built iteration** (v31 →
   IntegrityError on `stage_outputs` twice). Fix: VERIFYING recovers by re-verifying only; `_executing`
   moves to a new iteration whenever the current one is already built.
4. **One death counted twice.** Two supervisor passes 2 s apart (19:11) recorded heartbeat + "process gone"
   for the same death. Fix: the RECOVERING marker is created exclusively and stays until the relaunched
   worker starts (`engine._run` removes it); a lock holder always wins over the marker.
5. **Sleep killed a live worker.** The PC slept 03:27→19:11 during v30's browser probe; the wall-clock
   heartbeat age (56,643 s) made recovery kill the live worker. Fix: heartbeats carry sleep-excluded
   time (`supervisor.awake()`, QueryUnbiasedInterruptTime on Windows).
   **UNRESOLVED:** v31's worker (10956) vanished ~19:16–19:43 right after its build, with no traceback,
   WER record or recovery event: cause not established (the GUI that launched it was also gone by 19:43).
   No fix without evidence; record the next unexplained worker exit before changing anything.
   Side effect of 3 (found 2026-10-08): the failed rebuild wrote its file into `artifacts/v31/` before
   its transaction failed, so v31's bytes no longer matched the recorded sha256. v31 was restored from its
   recorded build output (sha256 match). The overwritten file is kept as
   `projects/P-20261003-bbad3c/v31-overwritten-by-failed-rebuild-2026-10-08-1946.py`. The 0.1.14 iteration
   guard makes a rebuild write to a new version folder.
6. D-AUTO-1 (scheduler) stays blocked until these fixes are verified live.
7. **Live check (0.1.14, 2026-10-08):** P-bbad3c was resumed at VERIFYING on the existing v31 (no v32).
   Result: FAIL with 4 major findings, all of kind harness → PAUSED `HARNESS_BLOCKED` (resume_state VERIFYING,
   iteration 31, no rebuild). Runtime steps that failed: "Home visible innerText from real browser" and
   "Fixture judgment with proven initial collapse and no reload". Both report the details markers in the
   rendered text: the harness reads collapsed `<details>` content via `--dump-dom`. 4/33 criteria unmet.
   **Next (AX Branch dev):** fix the verifier gaps named in the findings: visible-innerText browser
   evidence, exact Owner launch / browser-open observation, outbound-connection log, subprocess recording.
   Then resume to re-verify v31.
8. **Harness fixes 0.1.15/0.1.16, v31 re-verified again (2026-10-08, no rebuild, v31 unchanged by sha256):**
   - deterministic checks OK and Runtime Acceptance OK; all 4 BROWSER steps pass on visible innerText;
   - the 4 external attempts were all refused (0 unblocked); browser-open requests were recorded;
   - verdict still FAIL with 5 major findings, all harness → HARNESS_BLOCKED; 6 criteria unmet.
   The original 4 gaps are covered. What the verifier still asks for goes beyond them:
   - an offline environment on the exact Owner launch, which contradicts "exact";
   - interception of descendant processes and attribution of browser traffic (needs an OS firewall, so
     Owner-approved system setup);
   - a real default-browser launch;
   - a runtime test of startup failure ("prints error, waits for Enter");
   - the full Owner workflow observations;
   - complete subprocess/environment evidence.
   Owner decides: extend the harness for these, or accept/reduce the criteria. No further rebuild.
9. **0.1.17 approved-criteria gate, v31 re-verified (2026-10-08, no rebuild, v31 sha256 unchanged):**
   checks OK, runtime OK, 30/32 approved criteria met; 3 findings recorded as recommendations (not gating).
   FAIL on 2 approved criteria, both harness → HARNESS_BLOCKED:
   - #3: a real default-browser launch is not observed. Verification replaces the browser handler, so no
     window opens on the Owner desktop; the browser-open request itself is recorded. Persistence and port
     fallback: resolved.
   - #6: the rendered order of the result sections is not recorded, and the probe's 500 ms wait was not followed.
   Owner decides: accept the recorded browser-open request as evidence for #3 (or allow a real browser
   window during verification), and let the harness record the visible section order for #6.
10. **0.1.18, v31 re-verified (2026-10-08, no rebuild, v31 sha256 unchanged): PASS → OWNER_REVIEW.**
    - Owner ruling on #3: the recorded browser-open request plus server/port evidence counts in automated
      verification; the real window is checked at OWNER_REVIEW.
    - #6: the harness verified the click wait (all clicks settled: requests completed + 500 ms quiet) and
      the visible order: 한 줄 판단 → 핵심 근거 → 위험 요인 → 불확실성 → 확인해 볼 점 → 규칙 기반… → 상세 데이터 보기;
      inside the details, 시세 요약 → 기술 지표 값 → 가격 차트 → 재무·밸류에이션 → SEC 공시 → 외부 기사 → 판단 요소별 점수 → 데이터 출처 상태.
    - Deterministic checks and runtime: OK. 3 minor recommendations recorded (not gating). 0 unmet approved criteria.
    - **Owner next:** test v31, including the real default-browser window (`python -m axbranch review
      P-20261003-bbad3c --works` / `--broken "..."` / `--request "..."`).
11. **2026-10-08/09:**
    - The Owner's review of v31 led to v32, which failed verification (FAIL #30, 23:52).
    - The REWORK strategy call was then refused by both providers → PAUSED RateLimited (Claude reset 00:10,
      Codex 00:15). It stayed there because nothing re-checked a quota pause (fixed in 0.1.20).
    - 00:20: Claude available on one minimal call. Resumed the REWORK checkpoint with one worker (pid 26220).
    - Continuing REWORK rebuilt v33 (4 edits on v32) → verification PASS → OWNER_REVIEW 00:25.
    - The FAIL #30 strategy review did not run.

### Development continuation — GUI/live-view (2026-10-06, verification blocked)

- Preserved the existing GUI/live-view integration, session-lock retry, tests and development log.
  No merge conflicts or whitespace errors were found; no runtime projects or artifacts were changed.
- Fixed a status-refresh race in `supervisor.status()`: the engine can remove `ACTIVITY.json`
  between reading its contents and checking its timestamp. Treat that as a finished call instead
  of raising `FileNotFoundError` and interrupting the GUI refresh loop.
- Added a deterministic regression in `tests/test_live.py` that deletes the activity file immediately
  after it is read, then checks the local-work display and cleared provider pid/elapsed fields.
- Previous evidence: `devteam/DEV_LOG.jsonl` records 11 live tests and 106 full-suite tests passing
  before the pending GUI/lock changes. No later failing-test traceback was found in the repository
  results or `workspace/codex-delegation-6.log`; the precise reported failure is not yet reproduced.
- Follow-up diagnosis at 22:10 KST: the Python312 directory **is in PATH** (correcting the earlier
  PATH diagnosis). Commands run as `desktop-9kpek4l\codexsandboxoffline`. Direct Windows process
  creation for the absolute Python executable fails with `Win32Exception`, native error **5 / Access
  is denied**; file and ACL queries are also denied, so the exact denying ACL entry cannot be read.
  No accessible alternative Python was found in the checked existing installations/tool directories.
- Both targeted tests (`test_live`, `test_gui`, `test_lock`, `test_supervisor`) and full discovery
  were attempted again using that absolute executable. Both were blocked before unittest started:
  **0 tests executed; no PASS/FAIL result**. Evidence: [execution log](evidence/2026-10-06-codex-test-access.txt).
  No permissions, sandbox settings, hook settings or installations were changed. No release or commit.
- Next: run `python -X utf8 -m unittest tests.test_live tests.test_gui tests.test_lock -v`, then
  `python -X utf8 -m unittest discover -s tests -t . -v` in a session with Python access;
  resolve any actual failures before declaring integration complete. Do not rebuild completed work.
- **Resolved 2026-10-07 (lead, host):** the Codex session's `supervisor.status()` race fix and its
  `tests/test_live.py` regression were reviewed and kept; they were committed inside a52fa9b (whose
  message does not mention them — recorded here). The host ran the suite: 112 tests pass (957f9d6).
  The real GUI failures were two other races, fixed in a52fa9b: Windows refused the heartbeat/activity
  `os.replace` while the window read the file, and the lock probe made a starting session exit Busy.

### Product backlog

#### BACKLOG — Hook failed (non-blocking for this task)

- The reported hook failure did not prevent shell commands, file edits, or direct process-launch
  diagnostics. Python's independent Windows error 5 is the current test blocker.
- Read the configured Codex Companion, Impeccable and Ponytail hook definitions. The current session
  rollout contains no structured hook failure record; the failing hook and its root cause remain
  unconfirmed. Investigate with the actual hook stderr/exit code when available; do not disable hooks
  or modify plugin configuration as part of the GUI/live-view work.

#### Existing product work

0. Done: Test #1 (P-20261003-bbad3c) SAVE & CLOSE, 2026-10-09, satisfaction 60/100.
1. Reduce operator dependence: automatic recovery re-plan when a plan is proven misdirected (needs evidence of a reliable trigger).
2. Record Owner review time (UNKNOWN today) to measure Owner Effort in minutes.
3. Owner decisions: close finished projects; stronger isolation needs a dedicated Windows account (Owner action).
4. Later: AI Intelligence digest ("what matters today"), AX Works seams once it has data.

## 0.2 preparation (0.1.21, 2026-10-09) — done; Test #2 not started

**1. Knowledge.**
- Archive notes are Korean-first and readable:
  요약 / 최종 결과 / 문제 → 원인 → 해결 / Verification Lessons / Owner Feedback / 남은 과제 / 재사용 지식 / Owner Effort.
- The complete original record is kept under Evidence.
- Test #1 note restructured in place under the Owner's file name. The pre-restructure note is backed up in
  `workspace/projects/P-20261003-bbad3c/`. No original content was lost; only the header line gained the restructure date.
- Satisfaction 60/100, reason (Owner): UI readability, information hierarchy, report design, Obsidian document readability.

**2. Retrieval.**
- The existing keyword retrieval in planning now returns the 재사용 지식 + 요약 of matching notes, with note,
  project and evidence location.
- Live check: two related goals (Korean and English) → P-20261003-bbad3c; an unrelated goal → nothing.
- No vector search (not needed at this vault size).

**3. Owner Effort.**
- `owner_effort` event at every close and restructure.
- Test #1: interventions 15, manual recovery 9, Owner Escape 10. All three count only from 2026-10-06 06:18;
  earlier values are UNKNOWN.
- Test #1: feedback rounds 9, rework rounds 39, verification rounds 35, automatic recoveries 12,
  elapsed 139.5 h, agent-active 374 min, satisfaction 60.
- Owner review minutes: UNKNOWN.

**4. D-AUTO-1** (implemented 0.1.21).
- Task "AX Branch Supervisor" is registered for the Owner's account: at logon + every 5 min, IgnoreNew.
- It runs the existing deterministic `axbranch supervise` pass (D-ORCH rules, supervise.lock, no AI).
- One Windows notification per waiting episode (OWNER_REVIEW / Owner decision).
- Every pass appends a line to `workspace/logs/supervisor.log`.
- Live: a real scheduled task in a throwaway workspace recovered a dead STAFFING worker (one resume, one worker,
  window closed) and then notified once. The real task: LastResult 0, pass logged.

**Remaining:**
- The task runs the source checkout; AXBranch.exe is 0.1.12.
- No supervision while the user is logged off (per-user task).
- The notification's real on-screen appearance is not Owner-confirmed.
- Owner review minutes are not recorded.
- Old findings have no kind (counted as 미분류).
- D-SEC-1 is open.

## Overnight autonomous development (2026-10-10) — in progress
Audit: `docs/AUTONOMY_AUDIT.md` (Codex, from code + `docs/evidence/2026-10-10-autonomy-audit-evidence.json`).
Ranked gaps:
1. goal-aware execution and stopping;
2. durable autonomous replanning;
3. strategy/hypothesis/attempt memory;
4. independent challenge with correct engine provenance;
5. preservation of verification contracts;
6. adaptive knowledge retrieval.

Plan (sequential, all touch engine.py; Codex implements, Claude integrates, local tests):
- T1 durable strategy review (gap 2);
- T2 attempt memory + exact-repeat guard (gap 3);
- T3 actual-producer provenance for verifier routing (gap 4);
- T4 stop-outcome classification (gap 1, minimal);
- T5 probe/criteria preservation in strategy (gap 5).

**HANDOFF (Claude usage limit reached, 2026-10-10):**
- T1 DONE in 0.1.27 (6e3d987): durable strategy review; Codex implemented, Claude reviewed and fixed;
  70 engine/supervisor/library tests pass.
- T2 DONE in 0.1.28: attempt ledger in strategy reviews + identical-build guard (Codex implemented; Claude limited it to product FAILs).
- T3 DONE in 0.1.29: verifier routed by the actual (recorded) producer; metrics attribute builds to it (Codex implemented).
- T4 DONE in 0.1.30: explicit stop outcome (VERIFIED/BUDGET_REACHED/EXHAUSTED/OWNER_DECISION_REQUIRED/BLOCKED/OWNER_STOPPED/CLOSING) recorded and in HANDOFF (Codex implemented).
- T5 DONE in 0.1.31: a strategy review cannot drop or weaken Runtime Acceptance probes (preserve_probes).
  The full run also exposed a T2 guard bug with refused bundle files; fixed.

**HANDOFF — overnight 2026-10-10 (complete; safe stop: planned high-value bounded tasks done)**
1. Start: 0.1.26, Library/Develop just shipped; no autonomy audit.
2. Audit: `docs/AUTONOMY_AUDIT.md`; six ranked gaps.
3. Implemented (0.1.27 → 0.1.31):
   - T1: an interrupted strategy review resumes before any rebuild, and the budget is re-checked;
   - T2: the attempt ledger (approach → outcome) goes to strategy reviews; identical failed rebuilds are not
     re-verified;
   - T3: the verifier is chosen against the engine that actually built the artifact;
   - T4: explicit stop outcome (VERIFIED/BUDGET_REACHED/EXHAUSTED/OWNER_DECISION_REQUIRED/BLOCKED/OWNER_STOPPED/CLOSING);
   - T5: strategy cannot lower the verification bar.
4. Codex implemented T1–T5 and their tests, and wrote the audit.
5. Claude chose and specified each gap, reviewed the diffs, ran all tests locally, and fixed integration issues:
   - T1: only the newest pending review counts;
   - T2: the guard applies only to product FAILs and compares refused files.
6. Cross-engine: Codex implemented, Claude reviewed. No separate Codex adversarial pass over T1–T5 (not needed for
   these bounded diffs).
7. Autonomy evidence (scripted, deterministic tests):
   - after a quota refusal the CEO re-plans before building;
   - repeated identical failures turn into a forced change of approach without spending a verification;
   - verification stays on a different engine after failover;
   - stop reasons are explicit;
   - checks survive strategy changes.
8. Tests: full suite 175 — all pass except one headless-Edge test that is flaky under load (passes alone).
9. Commits: 6e3d987, 69f38fa, 9a815bd, fc902cf, and the 0.1.31 commit.
10. Remaining:
    - gap 6 (adaptive retrieval during strategy/diagnosis) is not done;
    - research/operation execution strategies (gap 1, full) are not done;
    - no semantic duplicate-approach detection;
    - the headless-Edge test is flaky under load.
11. BLOCKED_OWNER_APPROVAL: none.
12. Owner decision: none required.
13. Next: gap 6 (knowledge.retrieve in _strategy/_owner_rework with provenance), then a real Develop run to observe
    the new attempt ledger and stop outcomes live.
 Next: T2 attempt memory + exact-repeat guard. Give Codex a bounded spec using
  `docs/AUTONOMY_AUDIT.md` §3, editing engine.py + tests only; then run tests locally (Python is blocked in Codex's sandbox).
- Nothing is BLOCKED_OWNER_APPROVAL.

## Executive-standard session (2026-10-10, from 0.1.31)
Highest-value gap found: Verification PASS went straight to the Owner, with no CEO judgment of Goal satisfaction.
- Evidence: Test #1's final CEO judgment said the core goal (real prices) had no evidence of being solved, yet the
  engine delivered it as done.
- Implemented:
  - 0.1.32: CEO executive acceptance (goal_satisfied / missing_evidence / next_action / directive). The CEO orders
    its own rework, bounded at 2 per Owner action and by the budget. Claude implemented; Codex wrote tests and an
    adversarial review (5 findings fixed, incl. a pre-existing re-verify-after-PASS bug).
  - 0.1.33: knowledge retrieval at re-planning (gap 6). Claude implemented after Codex hit its usage limit.
- Verification status: CODE_VERIFIED + INTEGRATION_VERIFIED (scripted engine). A REAL_PROJECT check is running
  in a throwaway workspace (scratchpad live-exec).

## Artifact Library + Develop (0.1.26, 2026-10-10)
- Project = record of the work, Artifact = what the Owner uses, Knowledge = vault notes.
- The Library is an index over the existing tables (no copies).
- Lineage = an immutable `develop_from` event per developed project; the exact base artifact is pinned and sha256-checked.
- Develop takes a goal only: the CEO gets the base artifact, plan, lessons, feedback and knowledge, then runs the
  normal lifecycle. Owner Escape 0 (GUI).
- Open:
  - first real Develop run (Owner);
  - sibling branches share a version number;
  - Library refresh is on open only.

## D-AUTO-1 (recorded 2026-10-06 20:57, Owner; implemented 0.1.21 — see above): recovery depends on a live UI or a prompt
**What works (verified in code):** one engine worker (`python -m axbranch run <id>`, launched detached by the
supervisor) runs the whole loop by itself: stage → VERIFYING → REWORK/strategy/replan → … → OWNER_REVIEW,
stopping only at a governed pause (approval, failure budget, NEEDS_DECISION). No prompt is needed for that.

**Defect:** nothing deterministic restarts the loop when the worker *process* dies (crash, PC sleep/reboot,
memory reap as on 10-06 08:39). `supervise()` runs only (a) every 30 s inside the open AX Branch window, or
(b) when someone types `axbranch supervise [--watch]`. With the window closed, a dead worker stays STALLED
until the Owner (or Claude Code) acts → an Owner prompt becomes the watchdog again. The Claude Code
background monitor used on 10-06 only observed status and cost Claude tokens; it drove nothing.

**Fix to build (local, no LLM, no new service):** a single OS-level supervisor — Windows Task Scheduler entry
(at logon + every 5 min, single-instance) running `pythonw -m axbranch supervise` once and exiting; registered
/ removed by an Owner-approved in-app setting. Plus: OWNER_REVIEW reached → Windows toast notification, so the
Owner never has to ask "is it done?". Acceptance: kill the worker with the window closed → recovery within one
interval → run continues to OWNER_REVIEW; no duplicate scheduler entries or processes.
