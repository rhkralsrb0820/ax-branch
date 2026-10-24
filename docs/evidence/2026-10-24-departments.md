# Department harness evidence — AX Branch 0.1.60 (branch dev/departments)

Design: department packages are shared, versioned files (`departments/<id>/department.json`). A project attaches
them; the attachment is a project event, so it is persisted, auditable and separate per project. The existing
CEO -> stage -> verifier -> rework engine delegates each stage to an attached department (or a recorded temporary
agent). No second engine was added.

## Completion criteria → evidence
1. **Attach, no duplicates, detach, persistence, restore after restart:**
   - `tests.test_departments.test_attach_is_persistent_per_project_without_duplicates`;
   - `tests.test_gui.test_departments_attach_by_drop_or_button_persist_and_detach` (drop, [프로젝트에 추가],
     duplicate refused, a reopened window restores the chips, detach notice "다음 위임부터 적용").
2. **Separation between projects:** the same test: project B stays empty while A has research and operations.
   Stage outputs and results are per project (stage_outputs, events).
3. **Real delegation and hand-off:**
   - `test_ceo_delegates_to_attached_departments_and_results_flow_forward`, deterministic: the planning context
     holds only summaries; each stage gets only its own department; the build receives the research output;
     verification still runs;
   - real E2E P-20261024-5dd942 (below).
4. **Unattached functions and unapproved permissions:**
   - `test_unattached_department_or_overreach_is_refused_before_any_work`: an unattached department, web without
     the network permission, and tools beyond the department are each refused before any work, with no artifact;
   - temporary agents (no fitting department) are bound by the attached departments' tools and network and may not
     take an unattached department's agent role: `test_temporary_agent_cannot_bypass_attachment_tools_or_network`.
     The enforced versus declared fields are listed in 2026-10-24-department-enforcement.md;
   - capabilities no package provides still go through the existing capability gap and resolver (unchanged;
     covered by test_capabilities).
   - Attaching never approves payment, credentials, publishing or contact (governance and approvals unchanged).
5. **Bounded replanning and resume after failure:** `test_detached_department_gets_no_new_work_and_replanning_resumes`.
   The real E2E also shows a verifier FAIL followed by one bounded rebuild.
6. **Regression of existing flows:** the full suite F160 (below) includes the existing project, approval and
   result-run tests.
7. **Tests on the final code:** F160 (below).
8. **Package:** see "Package check".

## Real E2E (small, real models) — P-20261024-5dd942, demo workspace
**Goal and setup.** An operations improvement memo from the existing verification-history CSV (100 rows).
Driver: Codex work folder `work/run_department_e2e.py`. Providers: Claude leads, Codex verifies.

**Developer interventions (everything a person or the driver did instead of the product):**
1. The driver, not the GUI, created the project and attached research and operations (`departments.attach`, the
   same function the window calls) and attached the CSV input.
2. Run 1: the driver's build-limit watcher (max 2 builds) cancelled the run after Codex had PASSED v2, during the
   CEO's acceptance call. This was a driver bug: it counted verifications instead of waiting for a REWORK state.
   The project paused with "Rejected: Claude Code: 오너가 중단했습니다".
3. The watcher was fixed to stop only in REWORK.
4. Run 2: the driver resumed the same project with `--resume` (`store.resume`, recorded as "department E2E driver
   resume"). That took 1 CEO call, then OWNER_REVIEW.

No engine code was changed between the runs. No verdict or result was edited by hand.

**Sequence (run 1 log, then run 2):**
1. CEO plans (Claude), with two stages, each delegated with a reason:
   - "검증 이력 근거 분석" → research;
   - "운영 개선 우선순위 메모 작성" → operations.
2. research (Claude, 126 s) returns findings with 8 evidence items and stated limits (hand counts; a machine
   recount is recommended).
3. operations (Claude) builds v1, citing "1단계 「검증 이력 근거 분석」".
4. Codex FAILS v1 for real defects: an unconfirmed state treated as confirmed, and an unmeasurable success metric.
5. Rework rebuilds operations only (the research output is reused), producing v2.
6. Codex PASSES v2.
7. The CEO's acceptance is cancelled by the driver bug, and the project is PAUSED.
8. Run 2 resumes the project. The CEO accepts, and the project reaches OWNER_REVIEW.

**Result.** v2's numbers match the independent CSV baseline: 100/16/69/31, causes 26/8/35, status 34/35, stage
sums 27/15/0/134.

**Cost.** 7 calls in run 1 plus 1 in run 2; 471 s of provider time in run 1.

**Evidence.** `outputs/department-e2e/` (project.json, events.json), `outputs/department-e2e-run1.log`,
`-run2.log`.

**Limits of this E2E:**
- It ran on 0.1.59-labelled code from before the final fixes: the reused-stage ✓ display, the Tk timer fixes, the
  temporary-agent policy, the failed-drop notice and the `department` CLI. Those are covered by deterministic tests
  and F160d, not by this E2E.
- No temporary agent, refusal or detach happened in the real run. Those paths are verified only by deterministic
  tests.
- It is one run of one goal.

## Full suite and package (final code)
**Final full regression F160d** (the code is hash-identical to `tested-code-160d.sha256` in the Codex evidence
folder: 62 files):
- 413/414 in 47 audited batches with AXB_NATIVE_E2E=1; no test-job survivors.
- The one failure: `tests.test_runtime.RuntimeTests.test_browser_types_selects_confirms_and_asserts_a_crud_flow`,
  subtest `dialog:maybe`.
  - The browser step never finished: "browser did not finish within 90s (1 attempts)", `browser_exit_code` None.
  - The summary lists it under "not_run" because the subtest's failure split the result line; the log shows the
    FAIL.
  - Same failure class as F160b's: an unchanged browser test (runtime.py, sandbox.py and test_runtime.py are
    identical to main).
  - Run alone 3 times afterwards: 3/3 ok (219 s, 121 s, 120 s).
  - Not counted as a pass.
- Earlier runs:
  - F160 406/411, before the Tk timer fix;
  - F160b 410/411: test_runtime invalid_selector failed with the same Edge timeout. Isolated 10× per checkout:
    branch 8/10, main 9/10, same message (2026-10-24-F160b-runtime-failure.md).

**Package** `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\package-0.1.60\AXBranch\AXBranch.exe`:
- Rebuilt from the F160d code; sha256 77db6aa9…818f; departments bundled in `_internal\departments` (absolute
  `--add-data`).
- Checked on this PC with no mouse and window-only captures.

Department check in an isolated root (AXB_ROOT, test project P-20261024-773e2e set CLOSED so nothing runs):
- `AXBranch.exe department <id> attach research` → exit 0;
- the same again → exit 1 (duplicate refused);
- `attach operations` → exit 0;
- relaunch `--open`: both chips restored (ui/2026-10-24-pkg060d-relaunch-attached.png);
- `detach research` → exit 0; the same again → exit 1 (not attached);
- relaunch: only operations (ui/2026-10-24-pkg060d-relaunch-detached.png);
- events: attached research, attached operations, detached research; 0 calls.

Demo workspace:
- `--open P-20261024-5dd942`: `[리서치] → [운영]` pipeline, the research stage ✓ "이전 라운드 결과 재사용"
  (ui/2026-10-24-pkg060-departments-e2e.png);
- `--open P-20261023-2a0e75`;
- `result P-20261023-2a0e75`: health baseline / 77 labels; "Why was my transfer cancelled?" → failed_transfer →
  송금/이체팀;
- DB: call_start 37 → 37, training_run 4 → 4, owner_run 6 → 7.

## Not verified (stated plainly)
- **The drag gesture on the package itself.** No real mouse movement, by Owner rule. The drop logic, including
  the new "연결되지 않았습니다 … [프로젝트에 추가]" notice for a drop the hit test cannot place (outside, or
  covered by another window), is verified by `tests.test_gui` with the hit test patched. On the package, the same
  `departments.attach/detach` path was driven through the `department` command, and relaunch restore was seen on
  screen.
- **A real E2E on the final code.** The real E2E predates the final fixes (see its limits above).
- **Temporary agent, refusal and detach with real models.** Covered by deterministic tests only.
- **The Edge timeout's root cause.** It is intermittent, pre-existing and present on main.
- **Other environments.** Another PC, Windows without Python, and other display scalings.
