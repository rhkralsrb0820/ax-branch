# Development update — Outcome Attribution v1 (observational) phase CLOSED (2026-10-16)

Base commit d6764d0 (local, unpushed); all work uncommitted. Not a product artifact.
Checkpoint: workspace/checkpoints/2026-10-16-outcome-attribution-closed (SHA256SUMS; evidence/ holds every file below).

## Closure criteria
| Criterion | Evidence | Status |
|---|---|---|
| Implementation tests | tests/test_attribution 15/15; mutation: each of 7 fix points reverted -> killed by exactly one test (mutation_A2.log) | PASS |
| Sequential full suite | 284/284 OK, coverage-checked against 284 collected ids (A2_summary.txt); git diff --check clean | PASS |
| Codex independent review | A1 NOT_READY (4 defects) -> A2 READY_FOR_REAL_VALIDATION. Inspection only: Codex's sandbox cannot launch Python; execution evidence is Claude's (same engine, labelled) | PASS (inspection) |
| Historical replay (saved) | replay.py over a DB copy -> replay_v1.json (before fix 5) / replay_v1b.json (after); live DB sha256 identical before/after, copy row counts unchanged | PASS |
| Live integration | natural run P-20261016-3e5ca9 (below) | PASS |
| Observational | below | PASS (1 residual UNPROVEN) |
| No HIGH/CRITICAL attribution-integrity defect open | none | PASS |

## Defects fixed (defect -> evidence -> fix)
1. Rule exceptions in engine_breach / repaired_fails escaped the guard (invariant 5; Codex A1) -> both run inside
   `_attribute`; error recorded as UNKNOWN+error.
2. A harness repair could supersede an unrelated FAIL with a VERIFIED INFRA cause (Codex A1) -> a repair explains only
   the FAIL its probe review was opened for (pending -> verification) and never one with a verified non-harness cause.
3. Replay used a later `build_rejected` as evidence for an earlier FAIL (Codex A1; also found by Claude) -> rejection
   bounded by `at <= v.created`.
4. Responsibility named the configured provider after failover (Codex A1) -> provider of the final stage_outputs row.
5. `rule:no-deliverable` gave AGENT VERIFIED for a missing deliverable (Claude, historical replay vs established cause:
   P-20261003-bbad3c v15-v20 were transport/timeout failures of full-file regeneration, CHANGELOG 0.1.x "Fixed") ->
   AGENT ESTIMATED only; PRIMARY UNKNOWN; PRODUCT RULED_OUT. Replay diff: exactly these 7 FAILs changed.

## Historical replay (rules v1, 11 projects)
FAIL / rebuild subjects: PRODUCT VERIFIED 13, HARNESS VERIFIED 6, ENGINE VERIFIED 3, UNKNOWN 30.
Pauses: GOVERNANCE 8, OWNER_CONSTRAINT 5, PROVIDER 2 (explicit quota text), ENGINE 2 (internal IntegrityError), UNKNOWN 12
(provider timeouts stay PROVIDER ESTIMATED; NEEDS_DECISION / recovery checkpoints stay UNKNOWN).
Known cases reproduced: c88366 FAILs v1-v4,v6 HARNESS VERIFIED (any-status probe, Test #3) and rebuilds v2-v4 ENGINE
VERIFIED; cfa1d6 v1 PRODUCT, v2 UNKNOWN (+PRODUCT est.), v6 empty build UNKNOWN (+AGENT est.), v7 HARNESS VERIFIED.
Not observed in real history, so not claimed: INFRA (tests only), EVIDENCE / CEO_DECISION / EXTERNAL_DEPENDENCY (no v1 rule).

## Natural real validation P-20261016-3e5ca9 (Korean household ledger; dev channel; nothing staged)
- Goal -> 3 retrievals ADOPTED by the CEO at planning (R-5b95…, R-b045…, R-c182…) -> decision 1637 (plan v1) -> applied
  -> build action 1649 (carries the 3 retrievals) -> outcome 1655 artifact_built F-20261016-e8dba0 -> verify action 1660
  (artifact lineage) -> outcome 1668 verification FAIL V-20261016-084824 -> attribution 1669 (outcomes [1668]).
- Attribution 1669: PRIMARY UNKNOWN, PRODUCT ESTIMATED (model:Verification). Deterministic checks and runtime steps all
  passed; the FAIL rested on the verifier's reading of the busy-port observation. No convenient cause was invented.
- v2 rebuild: no ENGINE attribution (the FAIL carried product findings, so the rebuild was justified). v2 PASS
  (V-20261016-fd0910) -> no attribution (a PASS has no failure cause). State OWNER_REVIEW; `check` consistent.
- Live attributions == replay of the same rules over the same records (0 mismatches); 0 rule errors; exactly one
  attribution per FAIL, linked to its outcome id.

## Observational
- Code readers of attribution: only state.py (writer, attributions(), experience_chain view, HANDOFF summary) and
  attribution.pause_causes. No reader in engine routing, verdicts, budget, criteria, metrics, supervisor or governance.
- HANDOFF.md (which contains the summary) is written for developer engines/people; no AX Branch prompt reads it.
- Test: a crashing rule leaves the run's states, verdicts, iteration and budget identical (test_a_crashing_rule_changes_nothing_in_the_run).
- UNPROVEN (residual): a worker CLI could open project-folder files (HANDOFF.md) on its own initiative.

## Open, non-blocking (kept separate)
- DESIGN GAP: deterministic runtime OBSERVATIONS (e.g. `busy_port_second_launch.differs_from_busy_port=false`) are not
  failed steps, so v1 never makes them VERIFIED causes -> conservative UNKNOWN (under-attribution, not false blame).
- DESIGN GAP: no v1 rules for CEO_DECISION, EVIDENCE, EXTERNAL_DEPENDENCY (honest UNKNOWN).
- DESIGN GAP: replayed HARNESS_BLOCKED pauses read live attributions only (none in pre-hook history) -> UNKNOWN.
- DESIGN PREFERENCE (Codex): explicit rejection-event / stage-output ids in cause evidence.
- HIGH (separate phase): EVIDENCE_GAP verification execution capability (headers, PUT/DELETE, browser typing).
- Codex sandbox cannot execute Python on this host; host memory pressure.
