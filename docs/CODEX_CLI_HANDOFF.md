# Codex CLI handoff — AX Branch (kept current by Claude)

## CURRENT (2026-10-25): branch `dev/web-ui` (from dev/departments 82efe44), version 0.1.61, NOT merged into main
- The single structured status record is `docs/devroom/status.json`, shown in the web UI's 오너 개발실. Update it
  at each work unit: implementation status, verification level, verified commit, evidence, limits, next work.
  Never mark code as verified without evidence.
- Done on this branch:
  - `axbranch/actions.py`: shared Owner actions (the Tk window and the web API both use them).
  - `axbranch/web.py` + `axbranch/webui/`: local web UI.
    - Security: 127.0.0.1 only, per-start token, Host and Origin checks, no CORS.
    - Projects are created idempotently by request_id; GET never launches; no supervision loop.
    - Tests: `tests/test_web.py` (7); `tests/browser_web_selftest.py` runs headless Chrome with a temporary profile,
      20/20.
  - Engine 1: department `contract` format check (`departments.check_input` / `check_output`, engine notes-stage
    loop). Tests: `tests/test_departments.py` (12).
- Packages:
  - `demo-2026-11/package-0.1.61-web` (web, sha256 c02a2b8c…), with README-WEB.txt;
  - `demo-2026-11/package-0.1.60` (Tk, kept for comparison and recovery).
- **Running process started by Claude:** the web server `package-0.1.61-web\AXBranch\AXBranch.exe web` on the demo
  workspace, http://127.0.0.1:8765/, PID 47464. Stop it with `AXBranch.exe web --stop`. One Chrome tab was opened
  for the Owner.
- Owner confirmed (old Tk window): dragging a department into the HOME GOAL AREA attaches it. Nothing else about
  dragging is confirmed. Owner checks still open: README-WEB.txt items 1–3.
- **Next (Owner order, in sequence):**
  1. Engine 2: department acceptance criteria → independent verification. Deterministic criteria are checked in
     code; semantic ones go to the verifier; unmet or unverifiable is never PASS; conflicts are recorded with a
     replan decision.
  2. Engine 3: partial rework and resume. Re-run dependents of a changed stage; reuse or discard with recorded
     reasons (`stage_reused` exists); no duplicate runs; bounded retries.
  3. Engine 4: execution permissions. Separate declared / pre-approved / enforced at run time for the Owner's
     [결과 실행] versus verification; the smallest boundary that can be proven on this PC; ask the Owner before
     any OS change or new permission.
  4. Engine 5: per-phase timing of browser checks (launch / page ready / actions / selectors / exit). Track the
     Edge timeout as its own defect; do not raise limits.
  5. Then a small real department E2E (calls, tokens, time, interventions) and a final regression with hashes.
- Rules as before: no paid API, credentials or sensitive permissions without approval; never weaken tests; do not
  open or close the Owner's Chrome/Edge windows or use their profile, mouse or keyboard during development
  (headless with a temporary profile only); no main merge.

# Codex CLI handoff — department harness (kept current by Claude)

Repository: `C:\Users\HP\Desktop\AX-Branch\ax-branch`. Branch `dev/departments` (pushed to origin), based on `main`
11a36bf (0.1.59). Version 0.1.60, final reliability pass committed on this branch (see `git log`). Not merged into main (Owner).

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
- Reliability pass (final 0.1.60):
  - temporary agents are bound by the attached departments' tools and network and may not take an unattached
    department's agent role (`check_stage`, CEO rule); `temporary_agent` records its tools and web flag;
  - a drag drop that lands nowhere (or on a covered spot) says "연결되지 않았습니다" and points to
    [프로젝트에 추가];
  - `axbranch department <id> list|attach|detach` (also `AXBranch.exe department …`): the window's rules,
    mouse-free.

## After the reliability pass (2026-10-24, later)
- Real E2E on the final code: P-20261024-304eb4.
  - Pinned: commit 9483c1e, package 77db6aa9.
  - Sequence: research → operations, Codex FAIL then PASS, CEO accepted. 7 calls, 653 s, tokens recorded.
  - See `docs/evidence/2026-10-24-final-e2e.md`.
- The `code_generation` exception was traced: it allows writing only; execution runs through the engine's
  contained verification and the Owner's own launch. See the enforcement doc.
- Motion:
  - `axbranch/orb.py` particle sphere wired to real state in the composer;
  - preview: `python -m axbranch.orb` (상태 시뮬레이션);
  - see `docs/evidence/2026-10-24-orb-motion.md`.
- Package rebuilt with the motion: sha256 ef5f8b5a… (replaces 77db6aa9, which the E2E used).
- Owner checks open: `demo-2026-11/package-0.1.60/OWNER-DRAG-CHECKLIST.txt` (real drag, motion during a real
  run). None of these items is marked as passed.

## Evidence
- `docs/evidence/2026-10-24-departments.md`: the completion criteria mapped to tests, the real E2E, suites and the
  package check.
- Real E2E P-20261024-5dd942 (demo workspace): research → operations, Codex FAIL then PASS, CEO accepted. Driver
  and logs are in the Codex work folder
  `C:\Users\HP\Documents\Codex\2026-10-17\referenced-chatgpt-conversation-this-is-an`:
  `work/run_department_e2e.py`, `outputs/department-e2e*`.
- Tests:
  - F160d, final code, hash-matched: 413/414. The one failure is a headless-Edge 90 s timeout in an unchanged
    browser test; it passed 3/3 when run alone.
  - F160b's failure was isolated 10× per checkout: branch 8/10, main 9/10, same message.
  - See `docs/evidence/2026-10-24-F160b-runtime-failure.md`.
- Enforced versus declared department fields: `docs/evidence/2026-10-24-department-enforcement.md`. There is no
  OS isolation.
- Package: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\package-0.1.60\AXBranch\AXBranch.exe` (sha256
  77db6aa9…818f), README-DEMO.txt beside it.
  - Verified: department attach / duplicate / detach / relaunch restore in an isolated root; `--open` for 2 demo
    projects; `result` → the inquiry app, no model call.
  - The drag gesture itself was not done on the package (no real mouse).

## Exact notes carried from 0.1.59
- Selecting an agent shows its record: role and engine, department, why hired, task/instructions, its stage
  output, and for the Verification Agent every verification round with its findings and evidence.
- The 0.1.59 EXE did not check project navigation or [결과 실행] by click. In 0.1.60 both paths were checked on the
  EXE through `--open` and `result` (no real mouse clicks, by Owner rule).

## Remaining (not done)
- Merging dev/departments into main (left for the Owner/Codex decision).
- More departments beyond research and operations.
- Headless-Edge 90 s timeouts on this PC in browser runtime tests (intermittent, also on main; root cause not
  investigated, limit not raised).
- Real-model E2E of a temporary agent / refusal / detach (deterministic tests only).
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
