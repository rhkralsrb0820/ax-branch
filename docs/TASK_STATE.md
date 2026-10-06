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
