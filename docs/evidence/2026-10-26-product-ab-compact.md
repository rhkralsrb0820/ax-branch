# Product A/B — option (c) compact design (2026-10-26): pre-registered, NOT started (does not fit the cap)

**Owner decision applied.** Option (c): reduce the experiment, keep the 60,000 reported-token cap per project
(cache included), no output-only accounting, no increase.

**Attempt 1 is preserved unchanged** (`outputs/product-ab-786834f`, `docs/evidence/2026-10-26-product-ab-attempt.md`).
It demonstrated budget enforcement, not experience-reuse effectiveness; UNPROVEN.

## Correction of my earlier figure ("about 175,000")
The comparable packaged web text-rework E2E (P-20261026-3ca452, build 0.1.62-e62d440) was **measured, not
extrapolated**.
- Its actual total counted like the budget (input + output + cache creation + cache read) is **234,981 tokens**
  over 10 real calls: CEO plan 17,515; research 19,219; operations 24,767; verification 28,124; CEO acceptance
  20,416; CEO diagnosis of the text request 25,083; research 21,941; operations 26,449; verification 30,446; CEO
  acceptance 21,021.
- "175,000" was only its cache part (138,817 + 35,781). The attempt-1 evidence is corrected accordingly.

## What changed in the experiment (code, commit with this file)
- `python -m axbranch.product_experiment --design compact --root <NEW>`:
  - fixed tasks: A = `tutor`, B = `repair`; developer-designed evaluation input, NOT autonomous CEO opportunity
    discovery;
  - one concise proposal each: one customer/problem, one alternative, one value hypothesis, three compact cost
    scenarios, one MVP, one measurable next experiment; willingness to pay and revenue UNKNOWN;
  - no software, web research, contact or training;
  - the separate model-based task-selection run is removed;
  - same department contracts, experience retrieval and independent verifier.
- `PRE_REGISTERED.json` is written before anything else. It records the tasks, input hashes, department spec
  hashes, rubric and its hash, acceptance criteria, budget per project, experience policy (treatment only; A as the
  only source; cutoff; B-control outputs and evaluator judgments excluded), the planned intervention (one
  Owner-delegated heading revision on A), stop conditions and the estimate.
- **Feasibility gate:** the run refuses to start when even the MINIMUM of a project's measured per-call costs
  exceeds the unchanged cap. No model call is made on that path.
- **Prompt overhead: tried, then reverted.** Compact context JSON (same data) cut a scripted department run from
  38,334 to 35,991 prompt characters (−6%). But the full single-process run on cb4d834 then FAILED: 461 run, 9
  failures and 7 errors, because tests and scripted fixtures match indented prompt substrings. The change was reverted
  (engine.py byte-identical to 786834f; engine + harness_safety 116/116 after the revert). The fixed system rules
  dominate anyway: CEO rules 10,979 characters, verification rules 4,519 characters plus the schema.

## What actually ran
`outputs/product-ab-compact-1`: pre-registration, then the gate. **0 model calls.** Status NOT_STARTED_INFEASIBLE.

| Project | Calls | Measured per-call basis (attempt 1) | Estimate min–max | Cap |
|---|---|---|---|---|
| A (with one textual revision) | 8 | CEO 10,276–14,522; worker 7,049–12,959; edit 17,434; verify 15,504–20,080 | 96,595–128,641 | 60,000 |
| B-control (with independent evaluation) | 4 + eval | as above + evaluation 15,504–20,080 | 58,109–78,000 | 60,000 |
| B-experience (+ experience context ≤ 6,000 characters) | 4 + eval | + about 3,000 | 61,609–85,163 | 60,000 |

**Dominant measured cost.** The number of engine calls times their fixed per-call overhead: each CEO call is
10–15k reported tokens even for a tiny goal, and each Codex verification 15–20k. Task content is not the driver;
making the proposal shorter cannot bring A (8 calls) under 60k.

## What this shows / cannot show
- **Shows:** under the unchanged cap, the compact comparison cannot credibly complete, and the system refuses
  before spending.
- **Cannot show:** anything about experience reuse or quality. Still UNPROVEN.

## Smallest next changes (Owner decision; none applied)
1. **Remove the textual revision from the comparison.** That path is already shown twice through the packaged web
   E2E. A becomes 4 calls: estimated 43,105–62,083.
2. **Charge the independent evaluation to its own pre-registered evaluation budget** (e.g. ≤ 25k per evaluation)
   instead of the B project. B-control would be 43,105–62,083 and B-experience 46,105–65,083.

With 1 + 2, every production project fits at its measured MINIMUM, but the measured MAXIMUM still exceeds 60k by up to
about 5k. So the experiment could still stop at the budget; that would be reported as such, not rerun.
- A further reduction would be compact prompts for the CEO and verifier rules themselves: an engine change with
  regression risk, not proposed as a quick fix.
- Alternatively, the Owner could accept a modest per-project margin. That is a budget change, and is listed only
  for completeness.
