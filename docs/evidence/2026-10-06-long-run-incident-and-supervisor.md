# 2026-10-05/06 — the "2+ hour run" on P-20261003-bbad3c, and the supervisor that replaces the Owner as watchdog

Source: `workspace/axbranch.sqlite3` events (deterministic extraction, no LLM). All times local.

## What happened (22:02 → 00:22, 2 h 20 min)
The run was ACTIVE the whole time, not hung: six non-converging rounds (v10–v15), every one FAIL.

| Time | Event |
|---|---|
| 22:02 | resume (round 9 of the US-stock request); CEO diagnosis 198 s (claude) |
| 22:11 / 22:26 | data-source memo + verdict-rules stages (claude) |
| 22:51 | v10 full-file build, codex **1532 s** |
| 22:53 | claude usage limit → verification on codex (separate agent); FAIL |
| 23:25 | v11 build, codex **1791 s** (near the 1800 s timeout); FAIL |
| 23:27 / 23:33 | v12 (50 s), v13 (132 s); FAIL, FAIL — strategy "continue" twice |
| 23:57 | v14 build, codex **1337 s**; FAIL |
| 00:01 | strategy change_pipeline (first real change, after 5 FAILs) |
| 00:22 | final stage returned nothing → `build_rejected` (empty) → FAIL #11 = budget → PAUSED; process exited |

## Root causes
1. **Nothing watched the run except the Owner.** No heartbeat, no stall classification, no bounded recovery:
   the Owner had to ask a developer CLI "is it stuck?".
2. **Repeated root causes were retried the same way** (unparseable .py twice, VERDICT_SPEC.md missing three
   times, Markdown delivered as .py); strategy said "continue".
3. **The CEO misread a decline** ("Deliver without them") as "no network at all" while also choosing SEC/Stooq,
   so `network_access=[]` contradicted the plan; and a declined domain could never be asked again.
4. Full-file regeneration builds of a large program ran near the provider timeout.

## Fixes (0.1.10)
- `axbranch/supervisor.py`: deterministic status (ACTIVE / WAITING_FOR_OWNER / WAITING_FOR_PROVIDER / STALLED /
  RECOVERING / FAILED / PAUSED / COMPLETED) from SQLite + lock + `HEARTBEAT.json` + `ACTIVITY.json`; bounded
  recovery (resume → same signature again → replan+resume → NEEDS_DECISION; ≤5 per project; whole-tree stop of a
  hung worker; never launches while the old lock is held). The app runs it every 30 s; `axbranch supervise [--watch]`.
- Same failure signature twice in a row → forced strategy change (no "continue"), once per signature.
- Decline wording no longer reads as a network ban; strategy can revise `network_access`; a domain proposed again
  after a decline is a new pending request.
- Permission reuse: approved public read-only domains are reused; api_key / login / paid / posting / trading /
  personal data / destructive / governance always ask (fail-closed classification).
- OWNER_ESCAPE metric: Owner actions done through a CLI (`cli`, `developer_cli`) vs in-app; dev mode excluded.

## Live recovery evidence (no Owner CLI)
`axbranch supervise` classified bbad3c STALLED (REWORK, no session) → recovery `resume` (count 1) → detached
worker → the approval gate → WAITING_FOR_OWNER. After the re-request fix, all five runtime domains are pending
again (approvals #16–20: www.sec.gov, data.sec.gov, stooq.com, news.google.com [public_read];
www.alphavantage.co [api_key]). The project is waiting for the Owner's in-app decision; v8 (Owner-confirmed) is
untouched.
