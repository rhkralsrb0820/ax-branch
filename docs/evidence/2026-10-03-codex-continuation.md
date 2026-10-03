# Evidence: real Codex CLI continuation test — PASS (2026-10-03)

**Question:** can the local Codex CLI, given no task context, read AX Branch persistent state and
continue an interrupted project correctly?

## Setup (Claude Code session)
- Project `P-20261003-06983b` (Korean won amount → Hangul words) created and run live with
  `run --stop-at VERIFYING`: CEO plan (Claude), 1-stage pipeline, engineer stage (Codex) built
  `won_reader.py` v1 (sha256 `060710cb3b89…`). Session ended at VERIFYING, project left ACTIVE.
- Snapshot: `workspace/projects/P-20261003-06983b/BEFORE_CODEX.txt` (events ≤ 38; stage 0 output
  created 1791029149.143; P-20261003-906ead last event 27).
- Code at `a9cb062`, clean tree.

## Owner-launched command
```
codex exec -C "C:\Users\HP\Desktop\AX-Branch\ax-branch" -s danger-full-access -o "...\workspace\codex-continuation.md" "Continue the AX Branch work."
```
The prompt contains no project id, state or next step.

## What Codex did (its session log `~/.codex/sessions/2026/10/03/rollout-2026-10-03T21-08-10-01a101aa-….jsonl`, codex-cli 0.159.0)
1. Read README, CHANGELOG, PROJECT_STATE, TASK_STATE, ARCHITECTURE, DECISIONS; ran `axbranch status`.
2. Read AGENTS.md and the project's HANDOFF.md; ran `axbranch check P-20261003-06983b`; `git status`/`git log -1`.
3. Ran `axbranch run P-20261003-06983b` (the only active project).
4. Ran `check`, `status`, `git log -1`/`git status` again and reported.

## Verified from persistent state (not from Codex's report)
| Check | Result |
|---|---|
| Driving session was Codex | event 39 `session` env names include `CODEX_SESSION_ID`, `CODEX_THREAD_ID`, `CODEX_VERSION` (first session's env showed `CLAUDECODE…`) |
| SQLite state recovery | resumed at VERIFYING; VERIFYING → PENDING_CLOSE (event 43) |
| No completed stage rerun | stage 0 output unchanged (same row, created 1791029149.143); new calls only Verification + CEO report (events 40, 42) |
| Correct next action chosen | ran exactly `run` on the active project; left PENDING_CLOSE project untouched |
| Artifact/state consistency | `axbranch check` consistent for both projects; v1 disk sha256 == recorded |
| Owner-only project untouched | P-20261003-906ead: same `updated`, last event still 27 |
| Git visibility | HANDOFF `ax_branch_git.commit` = `a9cb062`; Codex reported the same; tree clean |
| PROJECT_STATE/TASK_STATE recovery | read by Codex before acting (commands 1–2) |
| Verification | PASS on Claude (independent of the Codex producer), 8/8 criteria, self-test exit 0, 3 minor findings |
| Independent artifact check | self-test exit 0; 0 mismatches vs an independent reference on 20,010 inputs; -1, 1.5, 10^12, '12' rejected |
| Final message | `workspace/codex-continuation.md` (written 21:10, after the run finished at 21:09:39) |

## Caveats
- The Codex session's environment also contained `CLAUDE_CODE_SSE_PORT` (inherited from the launching terminal); the CODEX_* thread/session ids are the distinguishing evidence.
- Codex ran with `danger-full-access` (needed: writes outside the repo, temp dir, nested `claude` CLI with network).
- Quota failover between providers is still not exercised live.
