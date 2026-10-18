# 0.1.40 source verification — 2026-10-18

Base: acc511c (0.1.39), plus inherited Claude WIP and Codex review/fixes.
Codex reviewed the source reader and engine integration directly; no second concurrent review process was run.

## Confirmed defects and fixes
- All sources inaccessible + empty claim list could pass; explicit unverifiable claims could pass;
  a fabricated contradiction quote could be downgraded without blocking. All now produce harness findings.
- Invalid URL, read timeout and unknown charset could escape and stop the engine. They now record unavailability.
- The reader now connects the exact checked numeric address, rejects mixed/private DNS answers, disables environment
  proxies and embedded URL credentials, and closes error responses. TLS retains hostname verification.
- Six regression cases failed on the inherited WIP (3 failures, 3 errors); 37 affected tests passed after fixes.
- Live HTTPS read: Python official Windows documentation returned 200, extracted text and a SHA-256 record.

## Final validation
All 358 discovered tests passed in 43 sequential Job Object-audited batches, with AXB_NATIVE_E2E=1.
No skipped, failed, unrun or bad batches. The real native EXE build-and-run test passed.
No processes remained in any audited test job after its batch. WMI/service/COM-created processes are outside this scope.
All 52 source/test file hashes were recorded and checked unchanged after testing.

Raw evidence: C:/Users/HP/Documents/Codex/2026-10-17/referenced-chatgpt-conversation-this-is-an/outputs/0.1.40-evidence
(F140_summary.json, F140_batches.jsonl, per-batch logs, tested-code.json).

## Limits and next work
Quotation presence is deterministic; semantic support and material claim coverage are model judgments.
Up to 40 sources / 2 MiB each / 100k verifier characters; inaccessible and non-text sources remain gaps.
Socket timeouts are not a total wall-clock bound for DNS or slow streaming. No clean Windows validation or new OS isolation.
Existing AXBranch.exe packaging is stale; already-running GUI processes must restart to load new source.
At release validation, Goal 1 v2 remains paused pending approved re-verification. Goals 2 and 3 are not yet run.
No production projects were resumed and no remote push was performed.
