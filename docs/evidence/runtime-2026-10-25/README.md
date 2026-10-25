# 실행 환경 진단 및 제출 거절 수정 — 2026-10-25

시작: `dev/web-ui` / `8a5530d`, clean. 새 기능 개발 중단. 공유 CODEX_REVIEW.md 최신 W2 후속 지적 확인.

## 서로 구분된 세 가지 오류

| 대상 | 실제 관찰 | 판단과 제한 |
| --- | --- | --- |
| Hook | `codex_core::hook_runtime`, `hook_name=legacy_notify`, `after_agent hook failed; continuing`, `os error 206` | 턴 종료 알림 명령 실행 오류. 도구 실행이 계속됐다는 로그가 있다. Python의 접근 거부나 Chrome의 실패를 이 Hook이 일으켰다는 근거는 없다. |
| Python | `Get-Item` / `Get-Acl`: `Access is denied`, `UnauthorizedAccessException`; PATH에 python/py 없음 | 현재 계정은 HP가 아닌 `DESKTOP-9KPEK4L\codexsandboxoffline`이다. 설치 경로 접근부터 거부돼 설치가 없다고 판단할 수 없다. HP 계정의 Python 레지스트리도 접근 거부. |
| Chrome | 브라우저 exit `2147483651`; GPU subprocess exit `-1073741790` = `0xC0000022`; `GPU process isn't usable` | 실제 headless Chrome 시작 실패. 프로필을 AppData/Temp에서 명시적 쓰기 허용 프로젝트 폴더로 옮겨 한 번 비교했으나 같은 오류. 정확히 거절된 하위 프로세스 객체/권한은 미확인. |

Hook의 현재 설정 명령(`C:/Users/HP/.codex/config.toml`에서 읽음):

```text
C:\Users\HP\AppData\Local\OpenAI\Codex\runtimes\cua_node\b2c4f0c90eadfac4\bin\node_modules\@oai\sky\bin\windows\codex-computer-use.exe turn-ended <JSON argument supplied by Codex>
```

확인한 최근 Hook 경고는 `hook-failures.json`에 보존했다. 예: 2026-10-25 12:59:25 KST의
`after_agent hook failed; continuing ... hook_name=legacy_notify error=파일 이름이나 확장명이 너무 깁니다. (os error 206)`.
전체 런타임 argv 길이는 로그에 없으므로 어느 인수가 Windows 한도를 넘었는지는 확정하지 않았다.
설정된 실행 파일 경로와 `turn-ended`는 확인했지만 알림을 다시 실행하지 않았다.
다른 Hook 신뢰 상태, 전역 보안 설정, notify 설정은 변경하지 않았다.

현재 sandbox 설정은 `windows.sandbox = "elevated"`. sandbox 설치 로그에는 HP 프로필 루트에
read-attributes ACE를 적용하려다 `MAXIMUM_ALLOWED ... os error 32`가 난 경고도 있다.
그 뒤 refresh는 `errors=[]`로 끝난다. 이를 Python/Chrome 실패의 확정 원인으로 단정하지 않는다.
ACL을 덮어쓰거나 sandbox 계정·레지스트리·방화벽 권한을 바꾸지 않았다.

Chrome 실행 파일과 같은 버전 `155.0.8059.40/chrome.dll`은 조회 가능하며 파일 버전도 일치한다.
관찰한 파일 ACL에는 Users와 제한된 Application Packages의 읽기/실행 허용이 있다.
Temp 폴더는 CodexSandboxUsers의 Modify 허용이 있다. 이 사실만으로 모든 Chrome 하위 프로세스의 접근이
허용된다고 판단하지 않았다. workspace-profile 실험의 원본 stderr·명령·요청 목록은
`chrome-workspace-profile.json`에 있다. `/`만 요청했고 자체 검사 완료는 **false**다.

## 최신 W2 지적 수정

- `actions.StartRejected`: 프로젝트 생성 전 입력 검증 거절에만 사용한다.
- API는 이 경우에만 HTTP 400 + `submission=rejected_before_creation` + 해당 `request_id`를 보낸다.
- 프론트는 정확히 일치하는 요청의 확정 거절에만 접수 ID를 지우고 목표·첨부·부서 수정을 허용한다.
- 응답 유실, 일반 400/500, 다른 요청의 거절, 생성 후 첨부 실패는 불확실한 접수 상태를 유지한다.
- 기존 접수 조회를 업로드 해석보다 먼저 잠금 안에서 수행한다. 부분 생성의 재시도는 기존 프로젝트를 돌려준다.
- 프로젝트 생성과 요청 ID 기록은 같은 SQLite 트랜잭션으로 묶어, 기록 실패 시 접수 없는 프로젝트가 남지 않게 했다.
- 실제 사용자 DB는 열거나 수정하지 않았다. 회귀 테스트는 격리 Store만 사용하도록 추가했다.

## 검증 순서와 현재 중단 지점

1. 관련 로컬 Node DOM 검사: 거절 수정 10 + 기존 중복 방지 12 + 프로젝트 10 + 뉴스 9 + 결과 4 = **45/45**.
   기존 35/35를 재사용하지 않고 이번 수정 후 실행했다. 실제 Python 서버/SQLite/브라우저/전체 회귀의 통과가 아니다.
2. Python API 관련 회귀: 잘못된 첨부·부서·base64의 생성 전 거절 → 수정 제출, 부분 생성, 접수 기록 실패 rollback
   테스트 추가. **실행 경로 접근이 막혀 미실행**. 같은 명령을 반복하지 않았다.
3. 실제 headless Chrome: 관련 Node 검사 뒤 workspace-profile 비교 1회. **시작 실패**. 사용자 Chrome·프로필·마우스는 사용하지 않았다.
4. Python 전체 회귀: 앞 단계 미통과로 미실행.
5. 보존형 새 빌드/BUILD.json: 미실행.
6. 텍스트 수정 요청 실제 E2E: 미실행. 모델 호출/토큰 사용 없음.
7. 서버 전환/오너 개발실 완료 상태 변경: 하지 않음. `docs/devroom/status.json`도 이번 작업에서는 그대로 둠.

JavaScript 구문 검사와 `git diff --check`는 통과. 모든 후속 검증은 이 수정 코드 기준으로 다시 해야 한다.

## 필요한 최소 Owner 조치

현재 세션 정책은 `sandbox_approval=false`라 이 세션에서 개별 비 sandbox 실행 승인 창을 요청할 수 없다.
보안 전체 해제나 전 Hook 신뢰는 필요하지 않다.

**먼저 Python만:** 세션의 읽기/실행 허용 경로에 아래 설치 디렉터리 하나를 추가해 달라고 요청했다.
DLL·표준 라이브러리도 필요하므로 exe 한 파일이 아닌 설치 디렉터리의 읽기/실행이 필요하다. 쓰기는 불필요하다.

```text
C:\Users\HP\AppData\Local\Programs\Python\Python312\
```

추가 후 실행할 첫 명령(설치/버전만 확인, 패키지 설치·credential 조회 없음):

```powershell
& 'C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe' -I -B -c "import sys; print(sys.version); print(sys.executable)"
```

세션 권한 추가가 불가능하면 HP 계정 PowerShell에서 위 단일 진단 명령의 결과만 받아 설치 여부를 먼저 구분할 수 있다.
등록된 설치가 확인된 뒤, 관련 Python 회귀는 아래 명령 하나로 시작한다.

```powershell
Set-Location -LiteralPath 'C:\Users\HP\Desktop\AX-Branch\ax-branch'
& 'C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe' -B -X utf8 -m unittest tests.test_web tests.test_inputs -v
```

**Chrome의 계정 차이 비교가 필요할 경우에만:** 관련 Python 검사가 통과한 뒤 다음 단일 명령을 HP 계정에서
실행하도록 한정 승인하거나 실행 결과를 제공하면, Codex sandbox 계정에서만 재현되는지 구분할 수 있다.
별도 프로필의 실제 headless Chrome과 로컬 HTTP fixture만 사용하며 사용자 Chrome은 조작하지 않는다.

```powershell
Set-Location -LiteralPath 'C:\Users\HP\Desktop\AX-Branch\ax-branch'
& 'C:\Program Files\nodejs\node.exe' tests/browser_web_regressions.js docs/evidence/runtime-2026-10-25/chrome-owner-account.json
```

이 명령 역시 미실행이며 승인/결과를 추정하지 않는다. `--no-sandbox`, GPU sandbox 해제, 관리자 실행,
ACL 전체 변경, 백신/보안 기능 해제, 사용자의 브라우저 재시작은 제안하거나 수행하지 않는다.

환경 복구 후 남은 순서는 **관련 Python 검사 → 실제 headless Chrome → 전체 회귀 → 보존 빌드 → 텍스트 수정 E2E**다.
모두 통과한 뒤에만 새 서버로 전환하고 오너 개발실을 갱신한다. main 병합/푸시 없음.

참고한 공식 문서: [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox),
[Permissions](https://learn.chatgpt.com/docs/permissions),
[Hook 신뢰와 실패](https://learn.chatgpt.com/docs/hooks),
[notify의 JSON 인수](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications).
`notify`가 JSON 인수 하나를 받는다는 공식 설명은 명령 길이 문제의 가능성을 설명하지만, 이번 argv 길이를 측정한 증거는 아니다.
