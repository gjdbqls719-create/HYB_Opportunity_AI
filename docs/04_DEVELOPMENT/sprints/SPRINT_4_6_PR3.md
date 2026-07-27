# Sprint 4.6 PR-3 — Opportunity Score Engine MVP

## 목표

정규화된 `OpportunityFactors`를 입력받아 가중 합산된 `OpportunityScore`를 생성하는 최초의 점수 엔진을 구현한다.

## 구현

- `OpportunityScorePolicy`
  - 기본 가중치: 가격 30%, 추세 20%, 수요 20%, 경쟁 15%, 위험 안전성 15%
  - 가중치 합계 및 등급 경계 검증
- `OpportunityScoreEngine`
  - Decimal 기반 가중 합산
  - 소수점 둘째 자리 `ROUND_HALF_UP`
  - 등급 판정
  - 외부에서 계산된 confidence 전달
  - timezone-aware 생성 시각 보장

## 공개 계약

```python
result = OpportunityScoreEngine(policy).calculate(
    factors,
    confidence=Decimal("80"),
)
```

`confidence`는 이 엔진이 추정하지 않는다. 데이터 충분성과 품질을 평가하는 별도 계층에서 계산한 값을 전달받는다. 값이 제공되지 않으면 아직 측정되지 않았다는 의미로 `Decimal("0")`을 사용한다.

## 범위 제외

- 요소별 원천 데이터 점수화
- Confidence 자동 계산
- 추천 및 설명 생성
- Marketplace/Category별 정책 선택

## 테스트

- 기본/사용자 정의 가중치
- Decimal 반올림
- 모든 등급 경계
- 입력·정책 검증
- timezone-aware 생성 시각
