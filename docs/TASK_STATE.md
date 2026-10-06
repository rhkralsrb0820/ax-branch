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

0. Owner: test the improved stock analyzer (P-20261003-bbad3c) and answer the two review questions.
1. Reduce operator dependence: automatic recovery re-plan when a plan is proven misdirected (needs evidence of a reliable trigger).
2. Record Owner review time (UNKNOWN today) to measure Owner Effort in minutes.
3. Owner decisions: close finished projects; stronger isolation needs a dedicated Windows account (Owner action).
4. Later: AI Intelligence digest ("what matters today"), AX Works seams once it has data.

## Open defect D-AUTO-1 (recorded 2026-10-06 20:57, Owner): recovery depends on a live UI or a prompt
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
