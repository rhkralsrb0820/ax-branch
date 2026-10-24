# Codex CLI handoff — AX Branch (kept current by Claude)

## LATEST (2026-10-25 06:50): HEAD ad9b3f4 (code 7fae36f), F161b 441/441
- Added since 02:40:
  - web artifact library + 이어서 개발 (`actions.develop`);
  - 오너 개발실 redesign (`status.json` schema 2);
  - preserved builds in `demo-2026-11/builds/` with BUILD.json;
  - web-path E2E harness `tests/browser_web_e2e.py` and two runs (`docs/evidence/2026-10-25-web-e2e.md`);
  - fix 7fae36f: the verifier gets the earlier stages' results.
- **Running:** the web server from `demo-2026-11/builds/0.1.61-ad9b3f4` (stop it with `AXBranch.exe web --stop`).
  The Owner's Tk window is untouched.
- **Codex review loop:** read `outputs/ceo-demo-review/CODEX_REVIEW.md`; write results to `IMPLEMENTATION_STATUS.md`
  there.

## CURRENT (2026-10-25 02:40): branch `dev/web-ui`, version 0.1.61, final code 7884507, NOT merged into main
- The single structured status record is `docs/devroom/status.json`, shown in the web UI's 오너 개발실. Update it
  at each work unit; never mark code as verified without evidence.
- Done (all tested on 7884507; F161 439/439, hash list in the Codex evidence folder `tested-code-161.sha256`):
  - shared Owner actions (`axbranch/actions.py`);
  - local web UI (`axbranch/web.py`, `axbranch/webui/`) and 오너 개발실;
  - engine 1: contract format check;
  - engine 2: department acceptance gate;
  - engine 3: cross-version reuse, dependents re-run, reasons recorded;
  - engine 4: Owner-run network allowlist — Python audit hook, best effort, not OS isolation;
  - engine 5: browser phase timing.
- Real E2E P-20261025-1d2aec on package 5a38799c (commit 90bb049): `docs/evidence/2026-10-25-e2e-161.md`. It
  found a contract false positive, fixed in 7884507.
- Final package: `demo-2026-11/package-0.1.61-web` (rebuilt from 7884507 plus this status record; its hash is in
  README-WEB.txt). The old Tk package `package-0.1.60` is kept.
- **Running processes:**
  - the web server `package-0.1.61-web\AXBranch\AXBranch.exe web` on the demo workspace, http://127.0.0.1:8765/,
    started by Claude. Stop it with `AXBranch.exe web --stop`;
  - the Owner's own Tk window (`package-0.1.60`): not started by Claude, left untouched.
- Owner checks open: README-WEB.txt items 1–3. Confirmed by the Owner: only the old Tk window's drag into the home
  goal area.
- Next: see the proposals in status.json. OS isolation needs Owner approval (admin rights).
- Rules: no paid API, credentials or sensitive permissions without approval; never weaken tests; do not touch the
  Owner's browser windows, profile, mouse or keyboard (headless with a temporary profile only); no main merge.

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
