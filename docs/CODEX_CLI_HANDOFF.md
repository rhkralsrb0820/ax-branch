# Codex CLI handoff — department harness (kept current by Claude at each work unit)

Repository: `C:\Users\HP\Desktop\AX-Branch\ax-branch`. Branch `dev/departments`, based on `main` 11a36bf (0.1.59).
Owner spec: department packages attached per project; 淸月 CEO delegates only to attached departments; results
pass between departments; independent verification is kept; then real state motion; then regression and the
demo package. Usage last measured (Claude CLI rate_limit_event): see the last line of this file.

## Done (uncommitted on dev/departments until the unit tests and the E2E pass)
- `axbranch/departments.py`:
  - validated, versioned packages loaded from `departments/<id>/department.json` (invalid specs are refused);
  - per-project attach/detach recorded as events (persisted, auditable, separate per project);
  - `check_stage` refuses an unattached department, tools beyond the department's tools, and web use without the
    network permission.
- `departments/research`, `departments/operations`: the first two packages (reasoning-only; no network or shell).
- `axbranch/engine.py`:
  - `STAGE.department`;
  - the CEO sees `attached_departments` (summaries) in planning, strategy and diagnosis;
  - `_staffing` enforces `check_stage` and records `department_delegation`, plus `temporary_agent` when
    departments are attached but none fits;
  - `_executing` re-checks before running (a detached department gets no new work) and gives each stage only its
    own department brief;
  - `department_result` records the evidence count and limits. Verification is unchanged.
- `axbranch/live.py`: stage titles `[부서] agent` / `[임시 에이전트] agent`; the record shows the department line.
- `axbranch/gui.py`:
  - sidebar "부서 라이브러리" chips (drag onto the composer or the project view; click for details with
    [프로젝트에 추가]);
  - composer [부서 첨부] with pending chips (attached when the goal starts);
  - the project view's "연결된 부서" row with ✕ detach ("다음 위임부터 적용").
- Tests: `tests/test_departments.py` (6) and `tests/test_gui.py` (+2 department tests). Results: departments 6/6,
  gui 13/13, live 14/14, engine+capabilities+executive_gap 124/124 (run 2026-10-24, not yet a full suite).

- State motion (step 3), uncommitted:
  - `home.StatusOrb` + `orb_state` derive the sphere from real stored states and supervisor statuses;
  - a timer runs only while work runs (or a ~2 s blink during an Owner wait); idle/error/done have no timer;
  - "모션 끄기" is persisted in workspace `settings.json`;
  - the pipeline statically highlights the current node and the hand-off arrow into it.
  - Tests: gui+home 19/19.
- Real E2E STARTED: project P-20261024-5dd942 in the demo workspace (research + operations attached; input
  axbranch_verifications.csv). Driver: Codex work folder `work/run_department_e2e.py --max-builds=2`; log
  `outputs/department-e2e-run1.log`; evidence `outputs/department-e2e/`. Re-running the driver resumes the same
  project (do not create a new one).

- Real E2E DONE: P-20261024-5dd942 OWNER_REVIEW at v2. Evidence `outputs/department-e2e/` and logs
  `outputs/department-e2e-run1.log`, `-run2.log`.
  - Delegation: research -> operations, each with a recorded reason. research's output (8 evidence items,
    stated limits) was used by operations; the memo cites it; its numbers match the independent CSV baseline.
  - Codex FAILED v1 for real defects; the rework rebuilt only operations (research reused); Codex PASSED v2;
    the CEO accepted. 7 calls, 471 s.
  - A driver bug of mine: the build-limit watcher cancelled the CEO acceptance after the PASS. Fixed (it now
    stops only a further rebuild) and resumed the same project (1 CEO call).

- 0.1.60 prepared (uncommitted): version + CHANGELOG; `--open <id>` (view only) and `result <id>` (= 결과 실행)
  for the exe and CLI. Related tests 41/41 (release, departments, gui, home, live).
- Full suite F160 STARTED on the final code (hashes in the Codex work folder
  outputs/0.1.40-evidence/tested-code-160.sha256; log F160_console.log, summary F160_summary.json).

- F160 result: 406/411. 1 FAIL: test_runtime collapsed_details (headless Edge did not finish in 90 s,
  environmental). 4 "not run": 3 GUI tests that PASSED but whose "ok" lines were split by Tk "invalid command
  name" output, plus one runtime test in a batch that took 1,398 s (StopIteration).
- Fixed a real defect the GUI output revealed: a direct refresh() call added a second refresh loop, and the orb
  timer was not cancelled on destroy. gui 15/15 clean.
- Full suite F160b STARTED (pid 19308 at start) on the fixed code: hashes in tested-code-160b.sha256; log
  F160b_console.log.

## Next, in order
1. Wait for F160b; if the runtime/Edge failures recur, investigate (runtime code was not changed in 0.1.60).
3. Full audited suite: `AXB_NATIVE_E2E=1 python -X utf8 outputs/0.1.40-evidence/suite2.py <TAG>` in the Codex work
   folder `C:\Users\HP\Documents\Codex\2026-10-17\referenced-chatgpt-conversation-this-is-an`.
4. Package: PyInstaller with `--add-data "departments;departments"` into `demo-2026-11\package-0.1.60`. Verify:
   project navigation and 결과 실행 on the EXE (a known gap from 0.1.59), plus attach -> run state -> result.
5. Version 0.1.60, CHANGELOG, commit on dev/departments, push.

## Gaps carried from 0.1.59 (exact)
- Selecting an agent shows its record: role and engine, department, why hired, task/instructions, its stage
  output, and for the Verification Agent every verification round with its findings and evidence (verified
  in-process for all 5 agents of both demo projects).
- NOT checked on the 0.1.59 EXE itself: moving between projects by clicking, and [결과 실행]. These were checked
  in-process (execution disabled) and on the 0.1.58 package for the same code paths.

## Rules (Owner)
- No paid API, no new credentials, no global installs. No external publishing or customer contact. No
  governance relaxation. Never weaken tests.
- Do not resume the production law-firm project or held reviews. No full-screen capture; no real mouse movement
  for checks; use a DB copy with execution disabled for screen checks.
- Do not run heavy tests and model runs at the same time. Do not commit unverified work just to hand over.

## Running processes
- None started by Claude at the time of writing.

Usage (Claude CLI rate_limit_event, 2026-10-24): five_hour 51% left, seven_day 30% left.
