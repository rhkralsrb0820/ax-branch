# Real-model work runs — isolated roots, synthetic inputs (2026-10-28)

**Common setup.**
- Source 0bf9914, in-process from source (NOT the packaged exe). One run per task, no retry, budgets never raised.
- Driver: session scratchpad `real_task.py`. It writes `plan.json` (goal, inputs, departments, budget, stop
  conditions, commit) BEFORE any call, and `record.json` after.
- Roots: Codex work folder `outputs/real-<task>-0bf9914/` (own SQLite workspace). No Owner project or data was used.
- Tokens = reported input + output (plus Claude cache tokens), as the engine budget counts them. UNKNOWN never
  occurred.

## 1. Small business web app (inventory, stdlib server) — P-20261028-91e7ca → OWNER_REVIEW
- Budget: 16 calls / 2,400 s / 220,000 tokens. Departments: none. Used: **6 calls, 157,033 tokens, 433 s**.
- Calls:

  | # | Role | Provider | Time | Tokens |
  |---|---|---|---|---|
  | 1 | CEO plan | claude | 47 s | 17,153 |
  | 2 | developer | claude | 186 s | 29,072 |
  | 3 | verification | codex | 36 s | 29,388 |
  | 4 | developer rework | claude | 57 s | 36,102 |
  | 5 | verification | codex | 31 s | 29,718 |
  | 6 | CEO acceptance | claude | 28 s | 15,600 |

- **Rework: 1.** v1 was judged FAIL by the verifier: its self-test used localhost networking against the "no
  network" requirement. v2 PASS.
- No provider fallback; the verifier was cross-provider (producer claude, verifier codex).
- **Isolation:** the web-mode Runtime Acceptance ran entirely inside per-run AppContainers through the new server
  channel (4 isolated launches per verification, `serve=true`). Steps that passed in both iterations:
  - server start, self-test;
  - page, API, 404, headless-browser render;
  - survival, and the Owner's exact launch.

  The self-test also ran isolated.

## 2. Product planning document (product-planning required) — P-20261028-8252ff → PAUSED by the budget reserve (no overshoot)
- Budget: 10 calls / 1,800 s / 90,000 tokens. Used: **4 calls, 73,670 tokens, 174 s**.
- Calls:

  | # | Role | Provider | Time | Tokens |
  |---|---|---|---|---|
  | 1 | CEO plan | claude | 36 s | 16,255 |
  | 2 | product planner | claude | 76 s | 16,835 |
  | 3 | verification | codex | 41 s | 21,486 |
  | 4 | product planner rework | claude | 18 s | 19,094 |

- **First draft passed the deterministic document contract.** No `verification_call_skipped`: the empty
  `excluded`/`experiments` failure of both earlier A/B attempts did not recur.
  - This is one run; whether `PRODUCT_PLAN_RULES` caused it is not established.
- v1 content FAIL by the independent verifier: some VERIFIED claims did not cite tutor.csv month rows/columns as
  the criterion requires. Format passing did not substitute for content verification.
- After the rework, the v2 verification was **not started**: remaining 16,330 < 21,486. The reserve had been raised
  to this project's own measured verification call. The project paused with that reason.
- Total stayed at 73,670 ≤ 90,000. The approved budget was not changed and there was no retry.

## 3. CSV analysis report (research + operations) with a same-project revision request — P-20261028-b203f2 → PAUSED HARNESS_BLOCKED at the revision; engine defect found
- Budget: 16 calls / 2,400 s / 160,000 tokens. Used: **9 calls, 127,922 tokens, 288 s**.
- v1:

  | # | Role | Provider | Time | Tokens |
  |---|---|---|---|---|
  | 1 | CEO plan | claude | 35 s | 15,628 |
  | 2 | research | claude | 29 s | 7,556 |
  | 3 | operations | claude | 24 s | 10,658 |
  | 4 | verification | codex | 28 s | 18,460 |
  | 5 | CEO acceptance | claude | 20 s | 11,170 |

  v1 PASSED cross-provider; department contract checks passed (2 events).
- Revision (delegated test input, labelled; NOT the Owner): "add a 3-line 요약 at the top; keep the rest and the
  evidence".
- v2 calls:

  | # | Role | Provider | Time | Tokens |
  |---|---|---|---|---|
  | 6 | CEO re-plan | claude | 42 s | 18,491 |
  | 7 | research | claude | 35 s | 10,222 |
  | 8 | operations | claude | 28 s | 15,649 |
  | 9 | verification | codex | 43 s | 20,088 |

- v2 content: the 요약 section was added and the numbers match the data (inspected).
- **The verifier could not judge "keep the rest"**: "v1 원문 또는 비교 기록이 없어 … 보존 여부를 검증할 수 없다.
  현재 문서의 제품 결함이 확인된 것은 아니다". This is a harness finding, so the project paused HARNESS_BLOCKED (no
  product rebuild).
- **Engine defect (general to every revision):** the verification context of an Owner revision did not contain the
  version the Owner reviewed.
  - Fixed after this run: `Engine._previous_verified` adds `previous_verified_version` (a bounded unified diff
    from the latest PASS version) to the verifier context whenever `owner_rework` is present.
  - Deterministic test: `tests/test_revision_context.py`.
  - **Resumed after the fix (ac83d2e), same project and budget:** call 10 was the verification of the same v2
    (codex, 35 s, 20,689 tokens). It returned **PASS** with no findings, judging the change and its preservation
    against the diff.
  - The CEO acceptance call was then refused by the pre-call reserve: remaining 11,389 < 18,491. The project is
    PAUSED at 148,611/160,000, with no overshoot and no budget increase.
- **Measured cost observation:** for a summary-only change the CEO re-planned and re-ran BOTH research and
  operations (calls 6–8 = 44,362 tokens).
  - Reusing the unchanged research result would avoid part of this; not implemented (IB-6).

## Totals (this round's real-model work)
- 20 calls; 379,314 reported tokens (157,033 + 73,670 + 148,611); about 930 s of run time.
- No provider fallback, no UNKNOWN usage, no budget overshoot (two pre-call reserve stops).
- Verification levels:
  - web app: real-model + real AppContainer server channel, source;
  - product planning: real-model (stopped by budget reserve);
  - CSV: real-model v1 PASS; the revision v2 PASS after the engine fix; final CEO acceptance not reached
    (budget reserve).
  - None of these was a packaged-exe run, and none was confirmed by the Owner.
