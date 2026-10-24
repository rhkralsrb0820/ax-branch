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

## What this does and does not show
- Recorded as: **an intermittent timeout that also reproduces on main; root cause not identified.**
- `axbranch/runtime.py`, `axbranch/sandbox.py` and `tests/test_runtime.py` are identical on main and on this
  branch (`git diff main -- …` is empty).
- The same failure, with the same message, occurred on main, which has no department code. So the failure is not
  introduced only by the department change.
- The counts (2/10 on the branch, 1/10 on main) are too small to compare. They are not evidence for or against an
  environmental cause, and no cause (Edge, this PC or the harness) is claimed.
- The test was not weakened, skipped or retried, and the 90 s limit and the assertion are unchanged. The full
  regression was not repeated until it passed.

## Not done / open
- The root cause was not investigated.
- A longer limit or a retry would hide the failure, so neither was added.
- A red result of the browser runtime tests with exactly this message is this open issue. Any other failure in
  them is to be treated as a new defect.
