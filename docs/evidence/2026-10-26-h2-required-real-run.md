# H2 required department — one real-model run (2026-10-26) — reached OWNER_REVIEW

**Setup.** Source 85f8f00, the same commit as the full regression (479/479) and candidate build `0.1.62-85f8f00`.
The run was in-process from source, NOT through the packaged exe.

- Isolated root: Codex work folder `outputs/h2-real-85f8f00` (own SQLite workspace; no Owner workspace, no browser).
- Script: the session scratchpad `h2_real.py`.
- Departments: research `available`, operations `required`, recorded at start through `actions.start(required=...)`.
- Input: a synthetic 10-row inquiry CSV.
- Goal: a short markdown report of counts per team and the top type per team, with 3 operations recommendations.
- Opt-in budget: 14 calls, 1,800 s, 150,000 reported tokens, local documents only. One run, no retry.

## Result (measured from the project's events; `record.json`)
- Project P-20261026-3973d8 → **OWNER_REVIEW**, no pause.
- Totals: 7 calls, 216 s, **92,851 reported tokens** (cache included).
- Plan: research stage "문의 데이터 분석" → operations stage "보고서 및 개선 권고 작성". The CEO delegated a stage to
  the required department itself; both producers were Claude.
- Verification:
  - v1 FAIL → rework → v2 PASS;
  - both rounds by **Codex** (recorded producer `claude`, verifier `codex`: cross-provider).
- Department acceptance at v2: all 6 criteria `met` (research 3, operations 3), with verifier evidence.
- `required_unmet`: none. `delegation_refused`: none.

## What this shows / does not show
- **Shows:** with a required department, a real CEO plan included a stage delegated to it. The fulfilled path
  passed the acceptance check (recorded work in the current plan version plus all criteria met) and reached Owner
  review, with cross-provider verification.
- **Does not show:**
  - The blocking path with a real model. A plan that omits a required department, a renamed role, a mode change
    after staffing, stale work and quarantine are covered by deterministic tests only (`tests/test_required.py`,
    `tests/test_lifecycle.py`).
  - Behaviour of the packaged exe in a real run. The build had a packaged smoke only.
  - Any general quality claim. This is one task.
