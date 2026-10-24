# F160b's one failure: isolated reproduction — AX Branch 0.1.60 (dev/departments)

## The failure
- Test: `tests.test_runtime.RuntimeTests.test_invalid_selector_is_harness_but_missing_element_is_ambiguous`.
- Assertion (tests/test_runtime.py:82): `self.assertEqual(bool(step.get('probe_misconfigured')), invalid, step)`.
- The browser step was not ok:
  - problem: "browser did not finish within 90s (1 attempts)";
  - `browser_exit_code`: None;
  - Edge's stderr held only its own background errors (fallback_task_provider, edge_pooling).

  The step never reached the selector check, so the test cannot tell an invalid selector from a missing element.
- Where: the F160b full audited run (47 batches, `AXB_NATIVE_E2E=1`), 410/411.

## Reproduction (the test alone, sequentially, nothing else running on this PC's test side)
Script: `repro_runtime.sh <checkout> 10 <label>` (scratchpad), one `python -m unittest <that test>` per run.

| Checkout | Code | Result | Failing runs |
|---|---|---|---|
| dev/departments (0.1.60) | this branch | 8/10 ok | run 8 (118 s), run 10 (133 s): "browser did not finish within 90s" |
| main (git worktree) | before departments | 9/10 ok | run 10 (120 s): "browser did not finish within 90s" |

- Passing runs took 46–62 s on both checkouts.
- Free physical memory stayed at about 5.1–6.0 GB in every run, failing ones included.
- The main runs were made after the branch runs. No code was edited while the branch runs were going.

## Change impact versus environment
- `axbranch/runtime.py`, `axbranch/sandbox.py` and `tests/test_runtime.py` are identical on main and on this
  branch (`git diff main -- …` is empty). The department work does not touch the browser path.
- The same failure, with the same message, happens on main without the department code.
- 2/10 against 1/10 is no measurable difference at this sample size (Fisher exact p ≈ 1.0).
- Conclusion: the failure is a headless Edge launch that intermittently does not finish within the harness's
  90 s limit on this PC. It exists before this change, and the department change did not cause it.
- The test was not weakened, skipped or retried. The 90 s limit and the assertion are unchanged.

## Not done / open
- The root cause inside Edge (why its headless start sometimes hangs) was not investigated. A longer limit or a
  retry would hide it, so neither was added.
- It remains a known intermittent environment failure (~10–20% per run on this PC). Treat a red result of this
  one test with this exact message accordingly, and treat any other failure in it as real.
