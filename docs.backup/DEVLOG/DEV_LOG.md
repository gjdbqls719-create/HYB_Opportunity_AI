# HYB Opportunity AI — DEV LOG

> 실제 기술 작업, 변경 파일, 테스트 결과, 문제와 해결 과정을 시간순으로 기록한다.
>
> 프로젝트의 역사와 장기적인 이야기는 `HYB_Development_Journal.md`, 현재 상태는 `PROJECT_CONTEXT.md`를 기준으로 한다.

---

## 기록 원칙

- 완료하지 않은 작업을 완료로 기록하지 않는다.
- 실행하지 않은 테스트를 통과했다고 기록하지 않는다.
- 사실, 추측, 향후 계획을 구분한다.
- 구조 변경은 이유와 영향 범위를 함께 적는다.
- Commit hash가 확인되면 기록한다.
- 한 개발 세션이 끝날 때 필요한 경우 갱신한다.

---

## 2026-07-23 — Project Audit v1

### 목표

현재 작업 프로젝트 전체를 점검하고, 원본 코드를 크게 변경하지 않은 안전한 공유용 Clean Version을 만든다.

### 기준 프로젝트

압축본의 내부 Git 저장소를 실제 최신 작업 프로젝트로 확정했다.

```text
HYB_Opportunity_AI/
└── HYB_Opportunity_AI/  ← 최신 Git 저장소 및 실제 작업 프로젝트
```

바깥 저장소는 과거 복사본이며 내부 최신 프로젝트 전체를 untracked 폴더로 포함하고 있었다. 이번 Clean Version은 내부 저장소의 내용만 프로젝트 루트로 사용한다.

### 변경 사항

- 공유본에서 `.venv/` 제외
- 공유본에서 `.pytest_cache/` 제외
- 공유본에서 모든 `__pycache__/` 및 `*.pyc` 제외
- 로컬 Secret이 들어갈 수 있는 `.env` 제외
- 로컬 SQLite DB 제외
- `.gitignore` 보강
- `docs/README.md`를 문서 인덱스로 개편
- 비어 있던 `docs/PROJECT_CONTEXT.md` 최신화
- `docs/DEV_LOG.md` 생성
- `docs/HYB_AUDIT_REPORT_2026-07-23.md` 생성
- Development Journal의 현재 상태 헤더와 Audit 기록 갱신

### 변경하지 않은 것

- Engine 계산 로직
- Marketplace API 동작
- 기존 공개 함수와 데이터 구조
- 테스트 기대값
- 기존 번호 문서의 삭제·이름 변경
- Git 이력 재작성

### 테스트

실행 명령:

```powershell
pytest -q
```

결과:

```text
98 passed in 0.68s
```

환경:

```text
Python 3.13.5
```

### 확인된 주요 문제

1. 압축본에 구버전 외부 저장소와 최신 내부 저장소가 중첩돼 있었다.
2. `.venv`와 테스트 캐시가 포함되어 공유 압축 용량이 불필요하게 커졌다.
3. `PROJECT_CONTEXT.md`가 비어 있었다.
4. 기술 작업용 `DEV_LOG.md`가 없었다.
5. 일부 번호 문서는 파일명과 실제 내용이 맞지 않았다.
6. 일부 미래 문서는 아직 도입되지 않은 기술을 현재 기준처럼 표현한다.

### 처리 원칙

이번 Audit은 안전한 정리를 목표로 하므로, 내용 유실 위험이 있는 문서 삭제나 대규모 파일 이동은 하지 않았다. 불일치 문서는 문서 인덱스와 Audit Report에 표시하고 다음 문서 정리 세션에서 하나씩 처리한다.

### Git

- Branch: `main`
- 최근 확인 Commit: `4302185 docs: add HYB development journal`
- 이번 Audit 변경: 아직 Commit하지 않음
- 추천 Commit: `docs: complete project audit v1 and refresh context`

### 다음 작업

1. Clean Version을 로컬 별도 폴더에 압축 해제
2. `.env`를 원본에서 안전하게 복사하거나 `.env.example`을 바탕으로 재작성
3. pytest 재실행
4. `git diff`와 `git status` 확인
5. 이상 없으면 Commit → Push
6. 이후 AI Analyst 기능을 테스트 우선으로 개발

---

## 새 항목 템플릿

```markdown
## YYYY-MM-DD — 작업 제목

### 목표

### 변경 파일

### 구현 내용

### 테스트

### 발생한 문제

### 해결 방법

### 주요 의사결정

### 남은 위험 또는 확인 사항

### Git
- Branch:
- Commit:
- Push:

### 다음 작업
```
