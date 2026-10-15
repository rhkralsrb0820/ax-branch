# Development update — Decision / Experience Trace phase CLOSED (2026-10-15)

Base commit d6764d0 (local); all work uncommitted. Not a product artifact.

## Closure criteria
| Criterion | Evidence | Status |
|---|---|---|
| Claude tests | full suite 277/277 OK (sequential batches, coverage-checked); git diff --check clean | PASS |
| Codex independent review | rounds 2 NOT_READY (2 defects) -> 3 NOT_READY (1) -> 4 READY_FOR_REAL_VALIDATION; workspace/handoff/CODEX_REVIEW_RESULT*.md. Limitation: Codex sandbox could not launch Python; its verdicts are by inspection, execution evidence is Claude's (labelled) | PASS (inspection) |
| Real validation | P-20261015-3a4f60 (see below) | PASS |
| No known critical/high trace-integrity defect | none open | PASS |

## Real validation P-20261015-3a4f60 (goal chosen by Claude in a domain with prior experience; nothing staged after)
- RETRIEVED (CEO, planning, K0 v1, exact query + sha): R-0b052a8938f9 (c88366 note, rank 1, score 6),
  R-7b8971860fb4 (bbad3c, rank 2), R-04728f89b426 (원화 금액, rank 3).
- decision_trace 1563 (call 1559): ADOPTED R-0b05… ("never -1 HTTP status; probes planned from v1"), ADOPTED R-7b89…
  ("no-arg launch = server, never self-test"), REJECTED R-0472… (unrelated domain, conflicting convention).
- decision_applied 1570: action 'staff and build', expects build -> action 1575 (decisions [1563], knowledge both
  lessons) -> outcome 1582 artifact_built v1 (F-20261015-e96deb). Chain COMPLETE, used_in_action True for the 2 adopted,
  False for the rejected. Plan check: 0 HTTP probes with status -1; no-argument-launch criterion present.
- v1 FAIL (V-20261015-90c893) -> v2 rebuild: action 1599 names NO decision (not a CEO decision) -> no lesson credit.
- Verification retrievals (6): role Verification, NOT_APPLICABLE, COMPLETE via verification -> verdict; no actions mixed.
- Provenance: 9/9 presented_sha256 recompute; source_sha256 = bytes read at retrieval; 7/7 calls carry prompt_sha256.
- Interruption: Claude's worker was killed (host low memory) during v2 verification; the supervisor resumed it
  (recovery 1607). The verify action key was reused (no duplicate), no orphan retrieval, no stale decision
  (2 decision traces / 2 applied). Owner resumes 0, automatic recoveries 1. Delivered v2 (V-20261015-c66345 PASS).
- Improvement from the lessons: UNKNOWN (no counterfactual; outcome attribution is the next phase).

## Defects fixed this phase (defect -> cause -> fix -> evidence)
1. False COMPLETE -> actions linked decisions by proximity -> decisions declare `expects` (build / verify+artifact / none);
   actions link only matching unconsumed decisions, newest wins, older recorded as replaced -> CausalLinkTests.
2. False used_in_action -> verification outcomes attached to builds by lineage -> outcomes only of the causing action;
   used_in_action requires COMPLETE + carried + outcome.
3. Verification retrieval semantics -> role-specific chain (NOT_APPLICABLE; verification -> verdict).
4. Provenance race -> source hash from the bytes knowledge.retrieve read.
5. Exact query/presentation -> exact query (+sha), presented item incl. retrieval_id, prompt_sha256 per call; id covers
   source+query hashes so a retry after a change records new provenance (Codex round 2).
6. Supervisor resume recorded as Owner -> Store.resume(by=); metrics episode rule (Codex rounds 2-3). Real DB:
   owner_resumes 25 -> 20, manual_recovery_replans 9 -> 7 (supervisor actions had been counted as Owner Effort).

## Open (not trace-integrity)
- HIGH: EVIDENCE_GAP missing_evidence does not reach executable verification; probe schema lacks headers/PUT/DELETE/typing.
- Codex sandbox cannot execute Python on this host (review = inspection).
- Host memory pressure kills long background jobs (tests, Codex, workers); supervisor recovery covered the worker.
