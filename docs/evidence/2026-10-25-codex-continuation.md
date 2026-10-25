# Codex 인계 후 수정 — 2026-10-25

기준: `dev/web-ui` / `1a8df78`, clean에서 시작. 최종 코드: `83a17dd`.
완료된 추천 카드·사이드바 화면 수정은 반복하지 않았다. main 병합·푸시 없음.

1. W1: 프로젝트/판정별 폼과 초안, 프로젝트 전환 시 기록 초기화, 이전 프로젝트의 지연 응답 및 오래된 버튼 거부.
2. W2: 제출 직전 sessionStorage에 요청 ID·목표·부서·첨부 메타데이터 저장. 새로고침/재시도 시
   GET `/api/submission`으로 기존 접수를 먼저 조회한다. 파일 내용은 저장하지 않으며 미접수 파일은 재첨부한다.
   불확실한 요청 ID로 다른 목표를 제출하지 않는다. 저장소 오류 시 제출을 막는다.
3. W3: 출처별 마지막 성공 수집 시각, 오래됨, 캐시가 있어도 갱신 실패 표시. 출처·게시일과 홈 최신 3개씩.
4. 텍스트 수정 실제 E2E: **미실행**. 기존 harness에 `--text-rework` 추가. 같은 프로젝트의 텍스트 요청 저장,
   DB의 Owner feedback → REWORK, 새 버전 독립 검증 PASS, 요청 문구가 있는 결과 열기를 요구한다.
   호출별 엔진·시간·토큰 원본, 실패 호출, 피드백·전환·개입·EXE 해시를 기록하고 실패 시 0으로 종료하지 않는다.

결과 열기 호출부 확인 중 라이브러리는 프로젝트 화면과 다른 경로임을 확인했다. 선택 프로젝트 ID를 바꾸지 않고
결과를 열도록 보완했다. App의 기본 Engine도 App workspace를 사용하도록 수정했다(공유 리뷰 후속 항목).

새 코드 검증:

- Node DOM fixture: W1 10/10 + W2 12/12 + W3 9/9 + 결과 열기 4/4 = **35/35**.
  DOM/서버 응답을 대체한 검사이며 실제 브라우저·SQLite·모델 실행의 증거가 아니다.
- `node --check axbranch/webui/app.js`, `node --check axbranch/webui/selftest.js`, `git diff --check` 통과.
- 파일 해시: `2026-10-25-codex-source-sha256.json`. 결과: `2026-10-25-codex-final-*-node.json`.
- 실제 headless Chrome: 별도 임시 프로필 사용. GPU subprocess 접근 거부로 시작 실패.
  `--disable-gpu`로도 실패했다. 브라우저 sandbox는 해제하지 않았다. `2026-10-25-codex-W1.json` 참조.
- Python 전체 회귀: 실행 전 Python 경로 접근 거부. **실행된 테스트 0개**.
  `2026-10-25-codex-python-blocked.json` 참조. 추가한 Python API 회귀도 미실행.
- 새로운 EXE 빌드·BUILD.json·서버 전환 없음. 기존 빌드와 서버는 유지했다.
- 실제 모델 E2E 호출 0회, 토큰 사용 없음, 프로젝트 실행 개입 0회. 실제 검증을 완료했다고 주장하지 않는다.

실행 환경 접근이 복구된 후 이어갈 순서:

1. `python -X utf8 -m unittest discover -s tests -t .` 및 실제 headless Chrome self-test.
2. 검증된 새 소스로 덮어쓰지 않는 `demo-2026-11/builds/<version>-<commit>/` 빌드와 BUILD.json 생성.
3. `python -X utf8 tests/browser_web_e2e.py <새 AXBranch.exe> <검증 CSV> <새 record.json> --text-rework`.
   별도 임시 root의 새 작은 프로젝트를 완료한 뒤, **그 프로젝트**에서 수정 요청한다. 기존 프로젝트는 재개하지 않는다.
4. 기록이 실제 기준을 만족한 뒤 상태 갱신 및 서버 전환. 자동 재시도·LoRA 학습·기준 완화 없음.

공유 리뷰는 읽었으나 공유 IMPLEMENTATION_STATUS.md 경로는 허용 쓰기 루트 밖이다.
검토 가능한 최신 보고서는 저장소 `outputs/ceo-demo-review/IMPLEMENTATION_STATUS.md`에 보존했다.
사용자 Chrome/프로필/마우스, 사용자 DB·산출물·오너 메모는 변경하지 않았다.
