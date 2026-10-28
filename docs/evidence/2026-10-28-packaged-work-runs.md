# Real work on the packaged candidate — 0.1.63-f53ed1e (2026-10-28)

**Build.** `C:/Users/HP/Documents/Codex/axbranch-builds/0.1.63-f53ed1e/AXBranch/AXBranch.exe`.
- exe sha256 `1c5fc46478cc4e0cc0805c19de4838fd43c61148bef5b0fa425c2c5d07f409c5`.
- Source f53ed1e: full single-process regression 542/542 OK, hashes matched (`outputs/0.1.40-evidence/FULL-f53ed1e-single-process.log`).
  The earlier run on 7a4e4cc was 540/542; its 2 GUI test-contract failures are kept as evidence.

**Method** (driver: session scratchpad `pkg_task.py`).
- Each task runs in its own isolated `AXB_ROOT`, with synthetic inputs and no Owner data (`AXB_GAI_DB` points to a
  missing file).
- The project is created with the same `actions.start` the web page uses, so the **task profile budget** is fixed
  at creation.
- All execution (planning, delegation, production, checks, verification, isolation, budget control, CEO
  acceptance) runs inside the **packaged worker** `AXBranch.exe run <id>`.
- The web page itself was not driven in these runs; that is a different verification level.
- One run per path, no retry.
- `plan.json` (written before any call) and `record.json` are in Codex work folder `outputs/pkg-<task>-f53ed1e/`.

**Provider availability.** Codex was at its subscription limit (until 2026-10-29 02:29), so every verification
fell back to Claude.
- This is labelled `SAME_PROVIDER_ROLE_SEPARATED`: a separate verifier role, NOT cross-provider independence.
- The fallback cause was first recorded as `unknown`. The Korean limit message ("구독 사용량 한도에 도달…") was not
  classified. Fixed in 7597373 (source; not in this build).

## 1. Product planning (profile product_planning, 150,000) — P-20261028-aa99e1 → OWNER_REVIEW, first pass
- 4 calls, **68,532 tokens**, 180 s:
  - CEO plan: 16,966;
  - product planner: 16,616;
  - verification: 18,729;
  - CEO acceptance: 16,221.
- The first draft passed the deterministic document contract (no `verification_call_skipped`).
- Verification PASS, with two non-gating recommendations. The CEO acceptance was reached and the project is in
  Owner review.
- Compare the source run of 2026-10-28 00:2x (90,000 budget, per-call reserve): stopped before the v2
  verification. Different run and budget, so this is an observation, not a controlled comparison.

## 2. CSV report + same-project revision (profile csv_analysis, 250,000) — P-20261028-e71d35 → OWNER_REVIEW twice
- **v1:** 5 calls, 61,580 tokens, 149 s:
  - CEO plan: 15,630;
  - research: 7,296;
  - operations: 11,120;
  - verification: 14,056 (PASS);
  - CEO acceptance: 13,478.
- **Revision** (delegated test input, not the Owner): "change only the title; keep the analysis, numbers, evidence
  and recommendations".
- **The research stage was reused**: `stage_reused`, `owner_revision=true`. Reason recorded: "The Owner asked only
  for a title change…". No research call was made.
- Revision calls: 4, 62,376 tokens, 115 s:
  - CEO decision: 18,902;
  - operations: 14,411;
  - verification: 16,200 (PASS);
  - CEO acceptance: 12,863.
- The verifier judged preservation against the reviewed version ("제목 외 내용은 바꾸지 말라고 지시했으므로 …
  남아 있는 것이 맞으며").
- Total **123,956 / 250,000** tokens; no budget stop.
- Observation, not a controlled comparison: the 2026-10-28 source revision without reuse spent
  CEO 18,491 + research 10,222 + operations 15,649 + verification 20,088 = 64,450 before reaching acceptance. Here the
  revision spent 49,513 before acceptance and then completed acceptance (12,863).

## 3. Web app (profile web_app, 250,000) — P-20261028-744f2f → PAUSED by the completion reserve; HARNESS DEFECT found
- 7 calls, **210,948 tokens**, 932 s:

  | # | Role | Tokens |
  |---|---|---|
  | 1 | CEO plan | 17,350 |
  | 2 | developer | 26,940 |
  | 3 | verification | 31,016 (FAIL) |
  | 4 | developer | 33,481 |
  | 5 | verification | 31,804 (FAIL) |
  | 6 | CEO decision | 19,455 |
  | 7 | developer | 50,902 |

- Next, the v3 verification was not started: remaining 39,052 < 51,259 reserved for verification + acceptance.
  No overshoot.
- **What worked in the package:** the isolated server channel. Server start, page, API, 404, headless-browser
  render and Owner launch all passed inside per-run AppContainers (`serve=true`) in both verifications. This is the
  first packaged evidence for the channel.
- **What failed:** the `--self-test` step "timed out (120 s), printed nothing" in isolation, in both rounds. The
  verifier treated it as a product failure. The developer rewrote the self-test without sockets; it still hung.
- **Root cause (reproduced from source, so not package-specific):**
  - Python 3.12 `tempfile.mkdtemp` calls `os.mkdir(path, 0o700)`, which on Windows sets a private DACL.
  - In the AppContainer that raised access denied, and `mkdtemp` retried forever. A faulthandler dump pointed at
    `tempfile.py:384 mkdtemp`.
  - With WRITE_DAC alone, the directory was created but its private DACL lacked the run's package SID, so the
    container could not write inside it.
  - The same artifacts passed instantly without isolation.
- **Fix (1fd997c, source; NOT in build f53ed1e):**
  - the private isolated runtime (v3) maps mkdir mode 0o700 to the run folder's inherited ACL;
  - `allow_custom_acl` defaults to True for run folders.
  - After the fix, all three real artifacts (v1, v2, v3) pass their isolated self-tests in 1–2 s, so **v1 would
    have passed**.
  - The two reworks (~126k tokens) were caused by this harness defect, not by the product.

## Summary of this round
| Path | Packaged result | Tokens |
|---|---|---|
| Product planning → verification → CEO acceptance → Owner review | **Completed** (first pass) | 68,532 |
| CSV report → review → same-project revision with stage reuse → re-verification → acceptance | **Completed** (research reused) | 123,956 |
| Web app → isolated server verification | Server channel **worked**; self-test blocked by a harness defect (fixed in source after the run) | 210,948 |

- Total: 20 calls, 403,436 tokens.
- All verification was same-provider (Codex at its limit), labelled, not cross-provider.
- Not done: a packaged re-run of the web app after the fix (needs a new candidate build).
