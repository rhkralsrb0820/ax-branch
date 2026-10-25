# Real web text-rework E2E — 0.1.62 candidate builds (2026-10-26)

**Harness.** `tests/browser_web_e2e.py --text-rework`: the packaged `AXBranch.exe web --test-mode` on an isolated
root; headless Chrome with a temporary profile (the Owner's Chrome was not used); real worker and models.
Records: Codex work folder `outputs/web-e2e-<build>/record.json`.

## Run 1 — build 0.1.62-3a7f432 (sha256 5ddad583…), P-20261026-53b987 — stopped at HARNESS_BLOCKED
1. From the page: goal, file and two dragged departments; then plan → research → operations.
2. Verification v1 PASS (6/6 department criteria met); the result opened in the page.
3. Text request on the SAME project (adding the heading "AXB-TEXT-REWORK"): persisted as `request` feedback,
   REWORK, same project.
4. The CEO re-planned v2 with ONE operations stage.
5. Verification v2 FAIL: "각 권고가 앞 단계 근거를 인용한다" unverifiable. The verifier's evidence: "stage_results
   is empty".

- 8 calls, 445 s.
- **Engine defect:** `_recorded_stage_results` read only the current plan's stages. Fixed in e62d440: the latest
  earlier plan version's notes-stage results are passed, labelled; with a regression test. No blind rerun before
  the fix.

## Run 2 — build 0.1.62-e62d440 (sha256 in its BUILD.json), P-20261026-3ca452 — ALL page checks passed
1. From the page: goal, file and two departments → project created.
2. v1 Owner review; the result opened in the page.
3. Text request on the same project → REWORK.
4. v2 back in Owner review, verified (PASS).
5. The revised result opened in the page with the requested heading "# 재작업 확인: AXB-TEXT-REWORK".
6. Department acceptance: 6/6 met in both iterations.

- 10 calls (CEO ×4, research ×2, operations ×2, verification ×2), 537 s.
- Tokens: output 60,363; Claude cache creation 138,817, cache read 35,781; input 20.
- The Claude CLI reported an equivalent cost of $2.33 (subscription; no per-call billing).

**Interventions and anomalies (stated plainly):**
- The text request was Owner-delegated test input from the page self-test, not real Owner feedback.
- Claude Code stopped the HARNESS process during run 2 because system memory was low. The page, the test server
  and the worker kept running, and the in-page self-test completed. The record was collected afterwards from the
  isolated database and the in-page report file. Then Claude stopped the test server and the headless Chrome.
- **Verification was NOT engine-independent in either run.** Codex CLI had hit its usage limit (bounded check:
  "You've hit your usage limit … try again at 5:41 AM"). The engine fell back to Claude for verification and
  recorded "verification ran on the producer's engine". The flow is verified; cross-engine independence for these
  runs is not.
- Observability gap found: the provider's specific unavailability reason is not persisted in the call events.

## Not verified
- Human drag and visual quality (Owner).
- The product A/B comparison: blocked while Codex is limited (no independent evaluator). Nothing was run;
  `product_experiment.py` requires a NEW root and was not started.
