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

## Open, in priority order
0. Owner: test the repaired stock analyzer (P-20261003-bbad3c v3) and report works / problem / change.
1. Owner: decide when to close the PENDING_CLOSE projects (906ead, 97494b, 4e3292, 46185d, d356e8); give a satisfaction score when closing (feeds the upgrade gate).
2. Owner: click through the exe once (goal -> report -> close) to confirm the human path.
3. Observe a genuine usage-limit failover when one occurs (timeout policy stays: pause).
4. Stronger isolation for generated code: dedicated low-privilege account + network block (needs Owner to create the account).
5. AX Works seams per `INTEGRATION.md` once AX Works has real data.
