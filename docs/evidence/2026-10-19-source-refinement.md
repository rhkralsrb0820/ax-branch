# 0.1.41 source delivery and bounded refinement — 2026-10-19

Base: 09058fa (0.1.40). Developed by Codex. Claude reviewed it independently and read-only
(REVIEW.md: two defects B1/B2, minor M1-M5, concerns C1-C5). Codex fixed B1/B2 with failing-first regression tests.
Claude re-reviewed the fixes and now leads development (Owner allocation: Claude 90%, Codex 10%).

## Changes justified by real Goal 1
- Bounded gzip responses are decoded. HTTP 200 client challenges count as unavailable content.
- An inaccessible PyPI project page falls back to explicitly labelled official JSON metadata. The record keeps
  the original failure, the actual API URL and the response hash. The labelled provenance is kept in the source
  summary and in the checked-claim note (B2).
- Exact spans are retrieved across sources within a 200,000-character evidence budget. Prior unresolved sources
  get priority, and earlier quote locations are kept where possible.
- After unverifiable claims, one bounded re-verification runs with refined evidence. It does not rebuild the
  artifact, relax criteria or treat earlier model judgments as facts.
- Browser: an attempt that made any app request is never repeated, by the retry or the fallback (B1). One
  installed alternative browser is used only when the first returned empty output with no app request.
  Changed behaviour: a timed-out attempt that already made app requests is no longer retried; it fails visibly.
- Source reads refresh the worker heartbeat, check cancellation between URLs and save unique evidence files.

## Validation (kept precise)
- F141b, full suite: 370/370 passed in 43 sequential Job Object-audited batches
  with AXB_NATIVE_E2E=1, including the actual native EXE build and run. No skipped, failed or unrun tests, bad
  batches, or surviving test-job processes. Code: tested-code-141-final.json, i.e. BEFORE the B1/B2 fixes.
- R141, after the B1/B2 fixes: tests.test_runtime + tests.test_sources 71/71 in
  8 audited batches, with no skips, failures or survivors. Code: tested-code-141-reviewed.json,
  re-checked unchanged at release. These are the only modules that exercise the changed lines (runtime._rendered,
  sources.check_claims, engine._source_evidence). The full suite was NOT re-run after B1/B2.
- The initial broad run (F141) had 357/366 passing: nine Edge empty-output failures, reproduced outside AX Branch.
  Installed Chrome passed the same local smoke.
- The process audit excludes processes launched indirectly by external COM/WMI/services. Durations include
  interruptions and are not benchmarks.

Evidence folder: C:/Users/HP/Documents/Codex/2026-10-17/referenced-chatgpt-conversation-this-is-an/outputs/0.1.40-evidence
(F141b_*, R141_*, per-batch logs, tested-code-141-final.json, tested-code-141-reviewed.json).

## Real-provider outcome and remaining work
Goal 1 P-20261018-279325 remains at v2. The earlier real run checked 23 claims: 18 supported, 5 unverifiable.
The next run (all roles on Codex) entered refinement, then hit the Codex usage limit on the second verifier call.
It paused with RateLimited, no consistency problems, and the capability revoked.
This is NOT a passed research Goal. Goals 2 (CSV) and 3 (EXE) are not started; they will run Claude-led.
No manual edits to runtime artifacts, no production project resumed, no remote push.

## Limits
- Quoted text presence is deterministic; semantic entailment and claim coverage remain model judgments.
- Retrieval is heuristic, not exhaustive, and API responses may fail. No clean Windows environment was tested.
- Socket timeouts do not impose a total DNS/slow-stream deadline. Cancellation happens between source URLs.
- Open review items: M1-M5 (minor) and C1-C5 (need run evidence); see REVIEW.md.
- The existing dist/AXBranch.exe is stale; this release changes source, not that executable.
