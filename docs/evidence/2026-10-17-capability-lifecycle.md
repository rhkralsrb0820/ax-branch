# AX Branch 0.1.37 개발·검증 기록

2026-10-17 (Asia/Seoul)

## 출발점

- 로컬 저장소: C:/Users/HP/Desktop/AX-Branch/ax-branch.
- 시작 브랜치 main, 미커밋 변경 없음. HEAD와 private origin/main 모두 50138e56aadda45ba1c98d86806a1cc0e3352e0e.
- 기존 상태: CEO/planner → specialist → deterministic checks/Runtime Acceptance → verifier → rework/replan.
  SQLite checkpoint, attempt ledger, provider failover, 승인 경계와 artifact 버전 보존은 이미 구현되어 있었다.
- 문서 일부는 0.1.33/진행 중 상태를 가리켰으나 실제 코드는 0.1.36이었다. 최근 코드·이력·DB 증거를 기준으로 판단했다.
- 실제 프로젝트 P-20261016-5fb8d6는 조사 시 EXECUTING v22였다. v21 실패에는 제품 결함과 함께 60초 검사 제한,
  지원하지 않는 native/upload/download 증거, 잘못된 probe가 섞여 있었다. 이 프로젝트의 artifact, DB, HANDOFF는 직접 수정하지 않았다.

## 구현

- Main Agent가 capability 목록, 지원하지 않는 검증, 실제 시간 제한을 보고 필요한 stage capability를 선언한다.
- 지원하지 않는 capability와 없는 browser harness는 production 전에 차단한다. 설치된 도구를 실행 능력으로 간주하지 않는다.
- 호출·검증마다 필요한 adapter/harness만 선택하고 attach/revoke 이벤트를 기록한다. 실제 provider의 호출 권한과 grant가 연결된다.
- 성공·예외·중단 시 회수한다. 비정상 종료로 남은 감사 기록은 project lock을 획득한 다음 종료 처리하며 권한을 재사용하지 않는다.
- 기존 승인·최소 권한·검증 기준·실패 분류·durable replan을 유지한다. governance.py 변경 없음.
- 프로세스 생성 실패 시 stream/임시 폴더/Job Object 누수, 중단 요청 이후 provider 시작 경로를 수정했다.
  실패한 Windows process resume도 중단·정리한다.
- 전체 회귀 실행에서 capability 감사 이벤트가 타임라인의 고용·배정 기록을 밀어내는 GUI 회귀를 발견했다.
  SQLite 감사 원본은 보존하고 화면의 최근 활동 선택 전에 attach/revoke를 걸러내도록 수정했다.

## 실행 증거

| 검증 | 결과 |
|---|---|
| 원본 baseline 전체 테스트 | 301개 통과 (2625.2초) |
| 변경 후 전체 discovery 실행 | 314개 실행, GUI 회귀 1건 발견 |
| GUI 회귀 수정 후 영향 모듈 재검증 | 31개 통과 (GUI/live/capability/release) |
| 최종 test id 대조 | 315개의 최종 결과 모두 통과; 전체 재실행 1회 통과로 합산 표기하지 않음 |
| 기존 테스트 보존 | baseline의 모든 test id가 변경 후 실행에도 존재 |
| 원본 코드 비교 | 신규 cleanup/cancellation 회귀 테스트 2개가 기존 코드에서 예상대로 실패, 수정 코드에서 통과 |
| 고정 모델 응답 + 실제 엔진·프로그램 실행 | FAIL/FAIL → pipeline 변경(plan_version 2) → PASS |
| capability 부족 | ml_training을 생산 전에 거부, artifact 없음 |
| 중단 복구 | 주입한 quota 중단 후 새 DB 세션/엔진으로 복구 → PASS |
| 실제 구독 provider | P-20261017-92de15 → PASS → OWNER_REVIEW |
| 감사·무결성 | 모든 demo grant 회수, consistency 문제 없음 |

실제 실행에서는 Claude가 구독 한도를 반환하여 Codex가 계획·제작·검증·최종 판단을 수행했다.
제작자/검증자는 역할이 분리됐지만 provider 다양성은 상실됐다. 이 사실은 기존 decision 이벤트에 기록됐다.
교차 모델 검증 성공으로 표현하지 않는다. 유료 API·설치·외부 배포·GitHub push는 수행하지 않았다.

## 재현

README의 기존 Python/sibling cheongwol 의존성이 있는 저장소에서:

```
python -X utf8 -m unittest discover -s tests -t . -v
python -X utf8 -m axbranch.demo --root <별도의-빈-폴더>
python -X utf8 -m axbranch.demo --live --root <다른-별도-빈-폴더>
```

각 demo 폴더에는 SQLite, evidence.json, 실행 artifact, HANDOFF가 남는다. 고정 응답 demo와 실제 provider 증거를 구분한다.

## 남은 한계

- 단순 CLI 목표의 실제 실행과 주입한 실패 경로를 확인했다. 임의의 복잡한 목표에 대한 autonomous 성공을 증명하지는 않는다.
- 필요 capability의 완전성은 planner의 선언에 의존한다. 자연어 목표의 누락된 요구를 모두 찾아내는 semantic detector는 아니다.
- Attach/revoke는 기존 adapter 선택·수명·감사 제어다. OS 권한 변경이나 파일/네트워크 격리가 아니다. D-SEC-1은 남아 있다.
- GPU/모델 학습, clean Windows 환경, desktop GUI 상호작용, upload/download harness를 새로 취득하지 않았다.
- 진행 중인 대형 법률 프로그램 프로젝트의 제품·검증 문제를 이 릴리스로 해결했다고 주장하지 않는다.
- 실행 중인 main checkout을 교체하지 않는다. 변경은 같은 실제 Git 저장소의 개발 브랜치와 별도 worktree에 보관한다.
- 기존 AXBranch.exe는 재빌드하지 않았다. 검증한 실행 대상은 0.1.37 소스다.
- 실제 model-driven 실패 후 재계획의 일반화, 의미적으로 같은 접근의 반복 탐지, 강한 OS 격리는 추가 검증/개발 대상이다.

원시 증거: baseline-tests.txt, regression-tests.txt, gui-recheck.txt, gui-live-final-tests.txt,
mutation-proof.txt, validation.json,
scripted-demo/evidence.json, live-demo-final/evidence.json, local-runtime-baseline.json.
