# Codex CLI handoff — department harness (kept current by Claude)

Repository: `C:\Users\HP\Desktop\AX-Branch\ax-branch`. Branch `dev/departments` (pushed to origin), based on `main`
11a36bf (0.1.59). Version 0.1.60, commit 608fdca. Nothing from this work is uncommitted.

## Done (0.1.60)
- Department harness:
  - `axbranch/departments.py` + `departments/{research,operations}/department.json`: validated, versioned
    packages; per-project attach/detach as events;
  - engine `STAGE.department`, enforced at staffing and before execution (only attached departments, tools and
    network within the department); `department_delegation`, `temporary_agent`, `department_result` records;
  - each stage receives only its own department brief; independent verification is unchanged.
- Window:
  - sidebar department library (drag onto the composer or a project, or click → details → [프로젝트에 추가]);
  - composer [부서 첨부]; the project's "연결된 부서" row with detach;
  - pipeline titles `[부서] agent` / `[임시 에이전트] agent`; a reused stage shows ✓ "재사용".
- Motion: `home.StatusOrb` from real state only (no timer when idle, in error or done); "모션 끄기" in workspace
  settings.json; the current pipeline node and the hand-off into it are statically emphasised.
- `AXBranch.exe --open <id>` (view only) and `axbranch result <id>` / `AXBranch.exe result <id>` (= [결과 실행]).
- Fixes: a duplicate refresh loop from direct refresh() calls; the orb timer is cancelled on destroy.

## Evidence
- `docs/evidence/2026-10-24-departments.md`: the completion criteria mapped to tests, the real E2E, suites and the
  package check.
- Real E2E P-20261024-5dd942 (demo workspace): research → operations, Codex FAIL then PASS, CEO accepted. Driver
  and logs are in the Codex work folder
  `C:\Users\HP\Documents\Codex\2026-10-17\referenced-chatgpt-conversation-this-is-an`:
  `work/run_department_e2e.py`, `outputs/department-e2e*`.
- Tests:
  - F160b 410/411: the one failure is an intermittent headless-Edge timeout in an unchanged browser test,
    which passed in 2 targeted reruns;
  - C160c 151/151 on the final code (affected modules).
- Package: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\package-0.1.60\AXBranch\AXBranch.exe` (sha256 519ce462...),
  README-DEMO.txt beside it.
  - Verified: `--open` for 2 projects, `result` → the inquiry app's health and classify, no model call.

## Exact notes carried from 0.1.59
- Selecting an agent shows its record: role and engine, department, why hired, task/instructions, its stage
  output, and for the Verification Agent every verification round with its findings and evidence.
- The 0.1.59 EXE did not check project navigation or [결과 실행] by click. In 0.1.60 both paths were checked on the
  EXE through `--open` and `result` (no real mouse clicks, by Owner rule).

## Remaining (not done)
- Merging dev/departments into main (left for the Owner/Codex decision).
- More departments beyond research and operations.
- Headless-Edge flakiness on this PC in browser runtime tests (intermittent, pre-existing code).
- Not verified: another PC, Windows without Python, other display scalings.

## Reproduce
- Tests: `python -X utf8 -m unittest tests.test_departments tests.test_gui tests.test_live`.
- Full suite: in the Codex work folder, `AXB_NATIVE_E2E=1 python -X utf8 outputs/0.1.40-evidence/suite2.py <TAG>`.
- Package: `python -X utf8 -m PyInstaller --noconfirm --clean --onedir --windowed --name AXBranch --paths
  ..\cheongwol\ceo --hidden-import cheongwol.connectors --add-data "<abs repo>\departments;departments"
  --distpath <out> axbranch_app.py`. Use an absolute --add-data source.

## Rules (Owner)
- No paid API, no new credentials, no global installs, no external publishing or customer contact, no governance
  relaxation, never weaken tests.
- Do not resume the production law-firm project or held reviews. No full-screen capture and no real mouse movement;
  use a DB copy with execution disabled, or the exe's `--open`/`result`.
- Do not run heavy tests and model runs at the same time.

## Running processes
- None started by Claude.
