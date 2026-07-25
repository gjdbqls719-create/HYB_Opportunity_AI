# Task 3.4.1 — Shipping Cost Intelligence

## 목적

수집 상품의 실제 배송비가 Opportunity 분석에 자동 반영되도록 하고, 사용자가 필요할 때 배송비를 명시적으로 재정의할 수 있게 한다.

## 동작

- `shipping_cost` 재정의 값이 없으면 `Product.shipping_cost`를 사용한다.
- 재정의 값을 지정하면 해당 값을 사용한다.
- 재정의 값 `0`은 무료배송 강제 설정으로 처리한다.
- 음수 및 유한하지 않은 배송비는 거부한다.
- 분석 결과에 `shipping_cost_source`와 `is_free_shipping`을 기록한다.

## 검증

- 기존 테스트와 신규 테스트를 함께 실행했다.
- 결과: `164 passed`
