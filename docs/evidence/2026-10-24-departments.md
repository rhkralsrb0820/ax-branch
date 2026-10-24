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
- Goal: an operations improvement memo from the existing verification-history CSV (100 rows). research and
  operations were attached by the driver (Codex work folder `work/run_department_e2e.py`).
- 淸月 CEO (Claude) planned two stages, each delegated with a reason:
  - "검증 이력 근거 분석" → research;
  - "운영 개선 우선순위 메모 작성" → operations.
- research (Claude, 126 s) returned findings with 8 evidence items and stated limits (hand counts, a
  machine recount is recommended).
- operations (Claude) built the memo citing "1단계 「검증 이력 근거 분석」". Its numbers match the independent
  CSV baseline: 100/16/69/31, causes 26/8/35, status 34/35, stage sums 27/15/0/134.
- Codex verification FAILED v1 for real defects (an unconfirmed state treated as confirmed; an unmeasurable success
  metric). The rework rebuilt only operations (the research output was reused). Codex PASSED v2, the CEO accepted,
  and the project is OWNER_REVIEW.
- Cost: 7 calls, 471 s of provider time.
- Manual intervention (developer): the driver's build-limit watcher cancelled the CEO acceptance after the PASS (a
  driver bug). It was fixed and the same project resumed with 1 CEO call. Evidence: Codex work folder
  `outputs/department-e2e/`, `outputs/department-e2e-run1.log`, `-run2.log`.

## Full suite and package
- F160 (first run): 406/411. 1 runtime/Edge timeout; 4 "not run": 3 GUI tests that passed but whose output lines
  were split by Tk "invalid command name" messages (a real timer leak, fixed), plus one runtime test.
- F160b, after the timer fix: 410/411 in 47 audited batches with AXB_NATIVE_E2E=1. The one failure,
  test_runtime invalid_selector, is a headless-Edge timeout ("browser did not finish within 90s") in an
  UNCHANGED browser test (runtime.py, sandbox.py and test_runtime.py are identical to main). That test and
  F160's failing one passed in 2 targeted reruns. Not claimed as a clean full suite.
- Last fix (a reused stage showed as not started) after F160b: C160c, audited batches of the affected modules on
  the final code (live, departments, gui, home, supervisor, engine, release): 151/151, no failures or test job
  survivors. Hashes: 2026-10-24-C160c-code-hashes.sha256.
- Package `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\package-0.1.60\AXBranch\AXBranch.exe`, rebuilt from the
  final code (sha256 519ce462...). Department definitions are bundled in `_internal\departments`. Checked on this
  PC with no mouse movement and window-only captures (PrintWindow):
  - `--open P-20261024-5dd942` shows the attached departments and the `[리서치] → [운영]` pipeline
    (ui/2026-10-24-pkg060-departments-e2e.png);
  - `--open P-20261023-2a0e75` shows the inquiry demo (ui/2026-10-24-pkg060-inquiry-demo.png);
  - `AXBranch.exe result P-20261023-2a0e75` (= [결과 실행]) started the inquiry app: health baseline / 77 labels;
    "Why was my transfer cancelled?" → failed_transfer → 송금/이체팀;
  - DB: one new owner_run; call_start 37 -> 37, training_run 4 -> 4 (no model call or training).
- This closes the 0.1.59 gap (project navigation and 결과 실행 on the EXE itself) except clicking with a real mouse,
  which was deliberately not done. Not verified: another PC, Windows without Python, other display scalings.
