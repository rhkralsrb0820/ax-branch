# Claude takeover — 2026-10-26 (dev/web-ui)

**Start state, verified at 00:49 KST:**
- `dev/web-ui` @ 5f70f97 with Codex's uncommitted product-planning, experience and budget work.
- The last repository edit was at 2026-10-25 20:10. No test or model process was running.
- The only process using AX Branch was the Owner's serving web server (`builds/0.1.61-67d9095`), left running.

**Source correction (2026-10-26, after Codex review).** I first reported the "AX BRANCH IN-PLACE EVOLUTION DIRECTIVE" as missing. It exists at `C:/Users/HP/.codex/attachments/358305e6-3b45-4598-a748-d8199e092b69/붙여넣은 텍스트.txt`; its 20 area names match `docs/IN_PLACE_EVOLUTION_REVIEW.md`. The missing-source claim is withdrawn.

## Stale records corrected
- **`docs/evidence/2026-10-25-product-takeover.md` said "Full regression: running".** The actual log
  (`product-takeover-regression.log`, 20:27) has no unittest summary. It ends with `invalid command name "…_tick"`
  and the fatal `Tcl_AsyncDelete: async handler deleted by the wrong thread`, so it is NOT a pass.
- "Headless browser: pending" is superseded by `product-takeover-browser.json` (20:11): 23/23, using a fake
  launcher and no model.

## Full-suite Tcl abort — root cause and fix
- **Position.** In discovery order, the first error is right after `tests.test_orb` (test 293 of 456). The abort
  follows in the threaded runtime tests.
- **Mechanism.**
  - Each `test_orb` test creates its own `tk.Tk()` root.
  - The orb's toplevel `<Map>` bindings and lambdas reference the orb, so a destroyed root stays in reference
    cycles that only the cyclic GC frees.
  - In a single-process full run, that GC happened on a later test's worker thread. Tcl aborts when an
    interpreter is freed off its thread. A pending orb `after` callback of the destroyed root also fired later
    ("invalid command name").
- **Classification.** A test-lifecycle defect in `tests/test_orb.py`, not application behaviour. The app has one
  Tk root, and `App.destroy` already runs `gc.collect()` on the Tk thread for this reason; `test_gui` relies on
  that.
- **Fix.** The `test_orb` tearDown cancels the orb timer, destroys the root and runs `gc.collect()` on the Tk
  thread. No test was removed or weakened.
- **Check.**
  - `test_orb + test_owner_run + test_permissions + test_runtime` in ONE process: 63 tests completed normally,
    with a summary and no Tcl error.
  - 1 failure, the known Edge timeout (below).
  - Also `test_gui + test_library + test_orb + test_engine` in one process: 118/118 (before the fix; it did not
    reproduce there).

## Edge timeout — first captured stall location (root cause still unknown)
- **Test:** `tests.test_runtime.RuntimeTests.test_rendered_page_is_checked_not_just_served`.
- **Phases:** first page request at 1797 ms, last at 2329 ms, 3 requests, 0 actions, end at 90047 ms
  (time limit).
- **Recorded `stalled_at`:** "page scripts / actions / virtual-time budget: requests seen, the browser never
  exited".
- **Reading.** Edge starts and loads the page; it then does not finish `--dump-dom` within its virtual-time budget
  (10 s for 0 actions) and stays until the 90 s limit. The stall is after page load, not at browser start.
- **Not done:** no limit raised, no retry added. Next: compare with Chrome on the same page, and check whether
  pending timers or connections keep virtual time from advancing.

## Targeted regressions (Claude, 2026-10-26)
- `tests.test_product_planning`, `test_departments`, `test_web`, `test_inputs`: 46/46. Then `test_product_planning`
  9/9 after the new restart test.
- New `test_restart_keeps_budget_and_never_duplicates_experience`: a fresh Store/Engine after a stop keeps the call
  limit, cannot re-open the budget, and records the stop's experience exactly once.
- Node experience UI fixtures 4/4; `node --check` on all webui scripts.
- Coverage present (Codex): arithmetic and unverified claims, malformed scenario names, version pinning,
  temporary-agent privilege union, scripted delegation/verification, bounded retrieval with no evaluation
  leakage, budget scope and missing usage, comparison leakage, small-sample HOLD.

## Not done yet in this record
Full single-process regression after the fix, candidate build, real web text-rework E2E, real product A/B. These
are tracked in the handoff.
