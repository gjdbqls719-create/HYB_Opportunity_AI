# New Chat Guide

## 새 채팅을 열기 전에 준비할 것
1. 최신 프로젝트 ZIP 또는 GitHub 저장소
2. 이 `HYB_STARTER_PACK` 폴더
3. `.env` 자체는 공유하지 말고 `.env.example`만 포함
4. 최근 실행 화면이나 오류 로그가 있다면 함께 준비

## 새 채팅 첫 메시지 예시

```text
HYB Opportunity AI 프로젝트를 이어서 진행하자.

첨부한 프로젝트 ZIP과 HYB Starter Pack을 먼저 읽고,
실제 코드 기준으로 전체 Audit을 진행해줘.

우리 협업 규칙:
- 나는 개발 초보자야.
- 수정 코드는 파일 전체로 제공해줘.
- 파일 경로, 저장 방법, 실행 명령어를 생략하지 말아줘.
- 한 단계씩 실행 결과를 확인한 뒤 다음으로 가자.
- 더 좋은 구조가 있다면 솔직하게 제안해줘.

Audit 결과를 먼저 정리하고,
그다음 Sprint 3 Opportunity Engine 개발을 시작하자.
```

## AI가 첫 번째로 해야 할 일
1. ZIP 압축 구조 확인
2. README와 Starter Pack 읽기
3. 실행 진입점 탐색
4. 의존성 확인
5. 환경변수 확인
6. 테스트 실행 가능 여부 확인
7. DB와 웹 화면 확인
8. 실제 상태 보고서 작성

## 첫 Audit이 끝나기 전 금지
- 무작정 새 폴더를 만드는 것
- 기존 기능을 확인하지 않고 전체 재작성
- 완료율을 추측으로 확정
- Production API로 전환
- 대규모 기능 추가

## 채팅이 길어질 때
다음 채팅으로 이동하기 전에 반드시 갱신한다.

- `02_CURRENT_STATUS.md`
- `03_NEXT_TASK.md`
- `07_DEVELOPMENT_HISTORY.md`
- 필요 시 `08_ROADMAP.md`

그리고 최신 코드와 Starter Pack을 함께 보관한다.
