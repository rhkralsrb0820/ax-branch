# AX Branch — TASK_STATE

| # | Task | Status |
|---|---|---|
| P0 | Audit repos, git state, reuse map | done (`AUDIT.md`) |
| P1 | Architecture + reuse map | done (`ARCHITECTURE.md`, `DECISIONS.md`) |
| P2–P4 | SQLite state, checkpoint/resume/handoff, Obsidian + GAI interfaces | done |
| P5–P7 | CEO / Verification boundaries, dynamic pipeline, Build→Verify→Rebuild | done |
| P8 | Provider abstraction + continuity | both CLIs run turns and drive sessions (live-proven); quota failover not live-proven |
| P9 | Minimal Owner UI | done (Tk window); not exercised end-to-end by a person yet |
| P10 | Real end-to-end run | done (`P-20261003-906ead`, v1 FAIL → v2 PASS) |
| P11 | Windows exe | built + launches; a full GUI run from the exe not yet done |

## Open, in priority order
1. Owner: approve the private GitHub push (`docs/GITHUB_PLAN.md`).
2. Owner: decide when to close the two PENDING_CLOSE projects (live test of SAVE & CLOSE → Obsidian).
3. Observe a real quota-limit failover when one occurs (timeout policy stays: pause).
4. Cross-process run lock (GUI + CLI on the same project).
5. Decide whether non-quota faults (timeouts) may fail over to the other provider (Owner policy; today: pause).
6. Multi-file / repo-editing artifacts; ax-works integration; Upgrade Proposal document generator.
