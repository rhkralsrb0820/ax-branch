# Product A/B comparison — attempt 1 (2026-10-26) — stopped by its own budget; NO comparison result

**Prerequisites met before starting:**
- full single-process suite on 786834f: 460/460 OK, code hashes matched (`tested-code-786834f.sha256`);
- one real availability call each: Codex "OK" (11,434 tokens), Claude "OK".

**Run.**
- `python -m axbranch.product_experiment --root outputs/product-ab-786834f`, from source at commit bcd2a84
  (code 786834f); new isolated root.
- Preserved candidate build `demo-2026-11/builds/0.1.62-bcd2a84` (fd65a29d…), NOT used by this source-run driver.
- Log: Codex work folder `outputs/product-ab-786834f.log`. Report: `outputs/product-ab-786834f/REPORT.json`
  (also `PRE_REGISTERED.json`).

## What happened (from REPORT.json)
1. **Task selection** P-20261026-a47117: the CEO selected two different catalog tasks, `tutor` (A) and `repair`
   (B), each completed with Codex verification.
   - 4 turns, 84 s, 45,468 reported tokens.
2. **Task A** P-20261026-a16736: CEO plan, then product planner, then Codex verification, then a product-planner
   rework.
   - 4 turns, 138 s, 64,995 reported tokens.
   - Then the budget guard stopped the project: "Execution budget: usage missing or reported token ceiling
     exceeded; no further call". The driver refused to auto-resume.
3. Not reached: A's second verification, the Owner-delegated text revision, B-control, B-experience and the
   independent evaluation.

Result: `passed: false`, `quality_improvement: UNPROVEN`, `comparison: null`. 8 calls in total. No quality claim of
any kind.

## Finding: the pre-registered budget cannot hold one full cycle
- `max_reported_tokens = 60000` per project. `knowledge.reported_tokens` counts input plus output, plus Claude's
  cache_creation and cache_read tokens, and Codex input.
- One verify → rework cycle already exceeded it (64,995).
- Measured reference (CORRECTED 2026-10-26): the comparable packaged web text-rework E2E (P-20261026-3ca452,
  10 real calls: plan → work → verify → text revision → rework → verify, both CEO acceptances) MEASURED 234,981
  tokens counted this way (input 20 + output 60,363 + cache creation 138,817 + cache read 35,781). An earlier
  version of this file said "about 175,000", which was only the cache part.

This is an experiment-design parameter, not a verification criterion. Changing it changes the pre-registration and
the subscription usage spent, so it is left for the Owner's decision; it was not rerun or edited.

**Options for the Owner (not applied):**
- (a) Raise the per-project reported-token limit (the earlier suggestion of about 200,000 was based on the uncorrected figure), keeping calls ≤ 12 and time ≤ 20 min per
  project. Estimated total about 4 projects × ≤ 200k.
- (b) Keep 60k but count only output tokens toward the cap. This changes the meaning of the cap and should be
  disclosed as such.
- (c) Shrink the tasks further.

Each needs a NEW root and a NEW pre-registration; the stopped root stays as evidence.
