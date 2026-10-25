# Codex 개발 진행

2026-10-25 12:03 KST 착수. dev/web-ui @ 1a8df78, clean 시작.
W1 개발 중. W2/W3/텍스트 수정 E2E 대기.
Python 경로는 현재 샌드박스에서 접근 거부. 새 코드 Python 테스트·빌드·실제 모델 E2E 미실행. 과거 테스트 결과를 이번 검증으로 사용하지 않음.

W1 구현 및 Node DOM 회귀 10/10. 증거 docs/evidence/2026-10-25-codex-W1-node.json. Chrome 시작 실패 증거 -W1.json. Python/패키지 미검증. W2 착수. 공유 디렉터리는 쓰기 허용 범위 밖이므로 이 저장소에 기록.

W2 구현: sessionStorage + 접수 조회 endpoint, 응답 유실/새 VM 새로고침/1회 생성 및 launch fixture/새 목표 ID/미접수 재시도/첨부 재선택 Node DOM 11/11. 실제 Python 서버 검증은 아직 아님. tests.test_web 접수 조회 회귀 추가(미실행).

W3 구현: 수집 시각·출처·게시일·캐시 유지 중 실패/오래됨·홈 최신 3개씩. Node DOM 9/9. 실제 Python 서버·공개 피드 수집 미실행. 새 패키지 빌드/서버 전환 없음.
