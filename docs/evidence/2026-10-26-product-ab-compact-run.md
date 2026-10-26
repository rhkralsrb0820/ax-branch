# Product A/B — compact run, Owner-approved design (2026-10-26) — STOPPED in Task A; no comparison

**Approved design.**
- Option (c), plus two approvals:
  - Task A's textual revision is excluded from this comparison. The revision path is evidenced separately by the
    packaged web E2E (P-20261026-3ca452) and was NOT re-verified here.
  - The independent evaluation has its own budget.
- Budgets: 60,000 reported tokens per production project (A, B-control, B-experience; cache included); 25,000 per
  B evaluation; experiment maximum 230,000. Existing call and time limits unchanged.
- Code: b088cdf. Root: Codex work folder `outputs/product-ab-compact-2` (`PRE_REGISTERED.json` written first;
  `REPORT.json`; `product-ab-compact-2.log`).
- **Preconditions:** one real availability call each at about 21:40 KST: Codex OK (11,500 tokens), Claude OK. 5.8 GB RAM
  free.

## What actually ran (all measured from the project's call events)
| # | Stage | Provider | Seconds | Prompt chars | Reported tokens | Running total |
|---|---|---|---|---|---|---|
| 1 | CEO plan | claude | 33 | 19,001 | 14,906 | 14,906 |
| 2 | Product planner (v1) | claude | 32 | 11,105 | 10,607 | 25,513 |
| 3 | Verification v1 | codex | 62 | 16,033 | 18,658 | 44,171 |
| 4 | Product planner rework (v2) | claude | 33 | 22,608 | 15,636 | 59,807 |
| 5 | Verification v2 | codex | 65 | 16,163 | 17,739 | **77,546** |

- **Totals:** 5 calls, 225 s of provider time, **77,546 reported tokens (all in Task A)**. Evaluation: 0.
  B-control / B-experience: not started.
- **Stop.** Before call 5 the project was at 59,807 (< 60,000), so the call was allowed. After it the total was
  77,546, so the next call was refused: "Execution budget: usage missing or reported token ceiling exceeded". The
  project paused and the driver stopped, with no auto-resume and no rerun.
- This is the known limitation: the stop applies after a call's reported usage, so an in-flight call overshot by
  17,546. The v2 verdict was not recorded.

## Diagnosis — why A needed a rework (measured cost of the rework: calls 4–5 = 33,375 tokens)
Verification v1 (Codex) failed on three findings:
1. **Length.** The proposal had 669 words against the CEO's planned limit of about 600.
2. **Deterministic product-planning document check.**
   - The contract requires the exact Korean headings 고객과 문제 / 경쟁과 대안 / 가치 가설 / 손익 시나리오 /
     MVP와 제외 / 수용 기준과 실험, and one fenced `product_plan` JSON block.
   - My compact task text described the sections in English ("one customer/problem, one alternative, …") and did not
     mention the JSON block.
   - The producer wrote "1) Customer & Problem", then in v2 "1) Customer & Problem (고객과 문제)". Both fail the
     exact-heading check, and v2 also lacked the JSON block.
   - The verifier noted that this check "does not establish those product defects".
3. **Department acceptance conflict.** The product-planning criterion "앞 단계 자료와 경험의 출처를 인용하고 … 차이·적용
   조건 …" cannot be met by Task A, which by design has no earlier stage and no experience.

**Conclusion.** The overrun came from an experiment-design mismatch (my task text versus the department's contract
and criteria), not from task size and not from an engine fault. The checks and the budget behaved as designed.

## What the comparison shows / cannot show
- **Shows:** under the approved budgets the run stops honestly; the contract and the department criteria are
  enforced; every token spent is accounted for.
- **Cannot show:** any experience-reuse effect, any quality difference, or evaluator behaviour. No comparison
  exists. General improvement stays UNPROVEN, and nothing is promoted.

## Smallest next change (proposal; NOT applied; needs Owner approval and a new pre-registration)
1. **Task text names the department contract explicitly:** the exact six Korean headings, the single
   `product_plan` JSON block, and the CEO's length limit. These are design inputs, so the change must be
   pre-registered.
2. **Product Planning's provenance criterion becomes conditional:** "cite earlier stages and experience when they
   are provided; otherwise state that none was provided". This is a new department version (1.0.1), pinned per
   project, so earlier projects keep 1.0.0.
3. **No budget increase is proposed.** A first-pass PASS for A, estimated from this run's calls 1–3 plus a CEO
   acceptance of about 10–15k, would be about 55–60k. That is still tight against the 60k cap, so
   B-experience remains at risk. This is an estimate from one run, not a confirmed minimum.
