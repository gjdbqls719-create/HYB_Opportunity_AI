# Sprint 5.2 PR-1 — Profitability Score Extension Point

## 목적

Discovery 분석값에서 생성되는 `price_score`의 현재 결과를 바꾸지 않으면서,
향후 여러 수익성 지표를 안전하게 결합할 수 있는 명시적인 확장 경계를 만든다.

## 배경

기존 `DiscoveryFactorPolicy.price_score()`는 ROI 하나를 직접 0~100 점수로
정규화했다. 계산 자체는 안정적이지만 메서드 이름만으로는 해당 점수가
가격 자체가 아니라 수익성을 기반으로 한다는 사실이 충분히 드러나지 않았다.

또한 향후 `margin_rate`, `landed_cost_roi` 같은 검증된 지표를 추가할 때
Adapter 내부에 계산 책임이 확산될 가능성이 있었다.

## 변경 사항

- `DiscoveryFactorPolicy.profitability_score(*, roi)` 추가
- Adapter가 새 수익성 점수 진입점을 사용하도록 변경
- 기존 `price_score(roi)`는 하위 호환 위임 메서드로 유지
- ROI Decimal 타입 및 유한값 검증 추가
- 기존 ROI 구간과 점수 결과는 변경하지 않음

## 의도적으로 포함하지 않은 사항

- `margin_rate` 또는 `landed_cost_roi` 가중치 적용
- 기존 `analysis` 계약 변경
- 새로운 Factor 추가
- Opportunity Score 가중치 변경

검증되지 않은 입력을 조기에 결합하지 않고, 다음 PR에서 실제 메타데이터의
생성 위치와 의미를 확인한 뒤 별도로 확장한다.

## 테스트

- 기존 ROI 경계값 결과 유지
- 기존 `price_score()` 호환성 유지
- Decimal 이외의 ROI 거부
- NaN 등 비유한 ROI 거부
