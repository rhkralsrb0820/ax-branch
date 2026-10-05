# Evidence: continuity under a real usage limit, PC sleep and a host interruption (P-20261003-bbad3c)

## Events (from SQLite, Windows System log, process table)
| Time | Event | Source |
|---|---|---|
| 10-04 02:16–02:27 | CEO strategy change_pipeline; design stage on Claude | events 236–246 |
| 10-04 02:27 | **Genuine Claude usage limit** ("resets 5:10am"); every Claude-preferred turn switched to Codex automatically (8 switches, no Owner relay) | provider_handoff events |
| 10-04 02:28–02:32 | v5, v6 built **empty** (0 bytes, sha e3b0c442…) by verifier-role producers; each still cost a verification call | artifacts, stage_outputs |
| 10-04 02:34:28 | last call started; **PC entered sleep 02:34:29** | event 291; Kernel-Power 42 |
| 10-04 16:18:00 | PC resumed (13.7 h later); provider timer counted the sleep → timeout; whole tree killed; project PAUSED with checkpoint | Kernel-Power/Power-Troubleshooter 1; event 292 |
| later | Claude Code's background-task reaper stopped the run and 5 watcher loops ("low memory while idle"). Windows logged **no** resource-exhaustion event. Cause on our side: 6 stacked watcher loops by the operator | task notices; System log |
| 10-05 15:44 | Recovery: no AX Branch / CLI / watcher process alive; state consistent; nothing re-run | process table; `axbranch check` |

## Root causes found and fixed (0.1.9)
1. Production stages were not given the source of the version being reworked (only the final stage got
   it, and the notes stages saw ≤ 60 000 chars) → stages answered BLOCKED. Now every stage gets the
   latest non-empty version and the Owner-confirmed version, in full.
2. The CEO staffed verifier roles as producers → empty deliverables. Now: production-only pipeline rule
   for plan/strategy/diagnosis, and empty builds are rejected deterministically (no verification call,
   no artifact, `build_rejected` event).
3. Rework baseline was "the latest artifact" even when empty → now latest **non-empty**.
4. Sleep counted as work → timeouts are sleep-aware (poll gaps > 30 s are not counted).
5. Strategy review could not change how usability is proven → it can now revise the runtime spec.
6. v4's open finding "rendered page unproven" was unanswerable → BROWSER probes (headless Edge runs the
   page's JavaScript; rendered text is checked, script source excluded).
7. Uncontrolled concurrency risk → machine-wide 2 provider slots + 1 GB free-memory floor.
8. A latent GUI abort (`Tcl_AsyncDelete`) when the cyclic GC ran on a worker thread after a dialog
   closed → cycles are collected on the Tk thread.

## Recovery decision
Plain resume would have reused stale BLOCKED notes and a verifier-as-producer final stage. Instead two
explicit `axbranch replan` calls (recorded as manual recovery actions): the CEO (Claude, limit reset)
rebuilt the pipeline (Claude spec → final producer), kept v4 as the base, and added 6 BROWSER probes
(19 runtime probes total).
