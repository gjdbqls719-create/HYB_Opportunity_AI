# Sprint 6 Summary — Explainable Decision Pipeline

## Status

Completed

## Evidence

- Git commit:
  - `dcedb13 feat: complete Sprint 6 explainable decision pipeline`
- Last confirmed full regression test:
  - **853 passed**

## Goal

Opportunity 분석 결과가 단순 점수로 끝나지 않고,
사용자가 판단 근거를 이해할 수 있도록
Engine부터 Dashboard까지 설명 정보를 전달하는 파이프라인을 완성합니다.

## Completed Outcomes

- Market Adjustment 결과의 설명 가능성 강화
- Decision Report와 Market Adjustment 연결
- AI Partner가 Decision Report 기반의 시장 설명을 사용하도록 연동
- Dashboard Decision Timeline 추가
- Decision Report 전용 테스트 및 전체 회귀 검증
- Explainable Decision Pipeline 완성

## Architectural Meaning

Sprint 6은 HYB를 단순 분석 엔진에서
설명 가능한 의사결정 지원 시스템으로 확장한 단계입니다.

```text
Analysis
→ Adjustment
→ Recommendation
→ Decision Report
→ AI Partner
→ Dashboard
```

각 계층은 자체 책임을 유지하면서
판단 근거를 다음 계층으로 전달합니다.

## Validation Note

이 문서는 저장소에 포함된 Git 기록과 기존 프로젝트 문서를 기준으로 작성했습니다.
Sprint 7 PR-3 문서 감사 과정에서는 코드 테스트를 다시 실행하지 않았습니다.
