## START HERE — 실행 환경 진단 checkpoint (2026-10-25 13:09 KST)
- `dev/web-ui`, 수정 코드 `b1275d9`. 이번 시작 기준 `8a5530d`, clean 확인. 새 기능 중단.
- 최신 공유 리뷰의 생성 전 제출 거절 후 수정 불가 문제 수정. 확정된 생성 전 거절만 ID 해제; 응답 유실/부분 생성의 중복 방지는 유지. 프로젝트와 접수 ID는 한 트랜잭션으로 저장.
- 이번 코드 Node DOM 45/45 및 JS 구문 통과. Python API 회귀 추가했으나 실행 경로 접근 거부로 미실행.
- 실패 Hook: `legacy_notify`, 현재 설정 `codex-computer-use.exe turn-ended`, Windows `os error 206`. Python 접근 거부/Chrome `0xC0000022`와 인과관계 근거 없음. Hook 신뢰/보안/notify 설정 변경 없음.
- 현재 셸은 `codexsandboxoffline`. Python 설치 경로 및 HP 레지스트리 접근 거부로 설치 유무를 확정할 수 없음. 경로 한정 읽기/실행 허용 요청 대기.
- Chrome 프로필을 workspace 안으로 옮긴 비교 1회도 동일 GPU 하위 프로세스 접근 거부로 종료. 실제 JS 검사 미도달. 같은 시도 반복 금지.
- 최소 Owner 조치·정확한 명령: `docs/evidence/runtime-2026-10-25/README.md`. 즉시 필요한 범위는 `C:\Users\HP\AppData\Local\Programs\Python\Python312\` 읽기/실행이며 쓰기/관리자 권한은 요청하지 않음.
- 다음: 관련 Python 검사 → 실제 headless Chrome → 전체 회귀 → 보존 빌드 → 텍스트 수정 E2E. 통과 전 서버 전환/오너 개발실 갱신 없음. 이번 `docs/devroom/status.json`은 변경하지 않음.
- 사용자 DB/산출물/Chrome/마우스 보존. main 병합/푸시 없음. 아래는 이전 checkpoint.

## START HERE — Codex checkpoint 2026-10-25 12:16:36 KST
- 브랜치 `dev/web-ui`, 코드 `83a17dd` (이후 문서 상태 커밋). 시작 기준 `1a8df78`, clean 확인.
- W1/W2/W3는 순서대로 수정·로컬 커밋. 현재 코드 Node DOM 35/35 및 JS 구문 통과. 실제 브라우저/서버/모델 검증 아님.
- **4번 실제 텍스트 수정 E2E는 미실행**. `--text-rework` 검증 절차만 준비됨. Python 실행 경로 접근 거부, headless Chrome GPU subprocess 시작 실패.
- 새 EXE 빌드/BUILD.json/서버 전환 없음. 기존 서버·DB·산출물·오너 메모 보존, main 병합/푸시 없음.
- 다음: 실행 환경 복구 → 전체 회귀/Chrome → 보존 빌드 → 같은 격리 프로젝트 텍스트 요청·REWORK·새 PASS·수정 결과 열기.
- 근거: `docs/evidence/2026-10-25-codex-continuation.md`. 보고: 저장소 `outputs/ceo-demo-review/IMPLEMENTATION_STATUS.md` (공유 경로는 쓰기 허용 밖).
- 이전 441/441과 이전 E2E를 이번 검증으로 사용하지 않음. 아래 인계 내용은 역사 기록.

## Codex 착수 — 2026-10-25 12:03 KST
- 브랜치 `dev/web-ui`, HEAD `1a8df78408931fb7fb3edc5d4402c5ea2ceb40fd`, 착수 전 작업 트리 clean. 인계 기준과 일치.
- START HERE와 공유 CODEX_REVIEW.md(07:53 KST) 확인. 완료된 화면 수정은 반복하지 않음.
- 첫 작업: W1 프로젝트별 승인/피드백 폼 및 지연 응답 분리. 이어서 W2 제출 복구, W3 뉴스, 텍스트 수정 E2E 순서.
- 기존 DB/산출물 보존, main 병합/푸시 없음. 사용자 Chrome/마우스 사용 없음.
- 현재 셸에서 인계에 적힌 Python 실행 경로를 찾지 못함. 실행 환경 확인 중이며 이전 테스트는 이번 검증으로 사용하지 않음.

# Codex CLI handoff — AX Branch (Claude usage at 8%: handed over 2026-10-25 ~12:00 KST)

## START HERE (Owner order of 2026-10-25, step 2 done by Claude, step 3 is yours)
- Repo `C:\Users\HP\Desktop\AX-Branch\ax-branch`, branch `dev/web-ui`, HEAD = this commit (code 67d9095).
  Not merged into main; do not merge.
- **Step 2 is DONE.** Codex's screen fix (devroom `.recommendation` card, sidebar saved titles) was reviewed and
  committed as 67d9095.
  - Tests: `tests.test_web` 10/10, `tests.test_gui`, headless Chrome self-test 23/23.
  - Built as `demo-2026-11/builds/0.1.61-67d9095` (AXBranch.exe sha256 c4ea707a…).
  - The demo web server was switched to it: http://127.0.0.1:8765/. The Owner must REFRESH their tab.
  - **No full regression on 67d9095.** F161b 441/441 is for 7fae36f and must NOT be shown as 67d9095's result.
- **Step 3, in order** (re-check `outputs/ceo-demo-review/CODEX_REVIEW.md` first):
  1. Switching projects in the web UI can leave another project's approval note or feedback text visible. The
     owner panel keeps `box.dataset.mode = mode + iteration`; key it by project id too, and clear the text when
     switching. Add a self-test.
  2. Duplicate project if the submit response is lost and the page reloads. The page creates `S.requestId` in
     memory only. Persist the draft request id in `sessionStorage` until the server confirms. On reload with a
     pending id, ask the server (`created_by`) instead of re-creating. Test with the server responding but the
     client dropping the response.
  3. News: show the fetch time and refresh failures per source (`home-feeds.json` has `fetched` and `error`), and
     show the latest 3 on the home screen.
  4. Then a real web flow on an existing project: send a TEXT change request (review with text) → REWORK →
     verification → result open. Use `tests/browser_web_e2e.py` as the model, on an isolated root with a copy of
     a finished project or a fresh small one. Record calls, tokens and interventions. Never resume unrelated
     projects. No LoRA training.
- After each unit:
  - commit;
  - update `docs/devroom/status.json` in plain Korean (keep Owner memos, they are in the workspace);
  - write `outputs/ceo-demo-review/IMPLEMENTATION_STATUS.md`;
  - build into `demo-2026-11/builds/<version>-<commit>/` with BUILD.json (never overwrite);
  - switch the server only after its checks pass.
- Do not open or close the Owner's Chrome. Use headless Chrome with a temporary profile only. No paid API, new
  credentials or sensitive permissions.

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

## Codex W1 checkpoint — 2026-10-25 12:06 KST
- 프로젝트·판정별 폼, 각 프로젝트 초안 보존, 지연 프로젝트/기록 응답과 오래된 폼 액션 차단 구현.
- 새 코드: node --check 및 Node DOM 회귀 10/10. 실제 Chrome은 GPU subprocess 접근 거부로 종료(통과 아님). Python/새 EXE 빌드/실제 모델 E2E는 접근 제한으로 미실행.
- 다음 W2 제출 ID 복구. 기존 서버는 변경하지 않음.

## Codex W2 checkpoint — 2026-10-25 12:09 KST
- 제출 직전 sessionStorage 기록, GET /api/submission으로 created_by 조회, 확인된 접수 복구. 파일 내용은 저장하지 않으며 미접수 첨부는 재선택 필요. 의도적으로 바꾼 목표에는 미확인 ID 재사용 금지.
- Node DOM W1 10/10 + W2 11/11; 서버 unittest 추가했으나 Python 접근 제한으로 미실행. 빌드/서버 전환 없음. 다음 W3.

## Codex W3 checkpoint — 2026-10-25 12:10 KST
- 출처별 마지막 성공 수집 시각·24시간 경과·갱신 실패를 캐시 유무와 무관하게 표시. 출처/게시일, 홈 최신 3개씩, 전체 목록 유지.
- Node DOM 9/9, JS 구문 확인. Python 캐시 보존/출처별 실패 회귀 추가했으나 미실행. 빌드/서버 전환 없음. 다음 텍스트 수정 E2E.
