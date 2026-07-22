# HYB Opportunity AI — Development Journal

> 이 문서는 HYB Opportunity AI가 어떤 문제에서 출발했고, 어떤 시행착오와 의사결정을 거쳐 현재 구조에 도달했는지를 기록한다.
>
> 기술적인 현재 상태는 `PROJECT_CONTEXT.md`, 협업 원칙은 `AI_CHARTER.md`를 기준으로 한다.
> 이 문서는 프로젝트의 **역사, 방향 전환, 배운 점, 주요 마일스톤**을 기록하는 사람 중심의 개발일지다.
>
> 초기 기록은 이전 대화와 기존 `DEV_LOG.md`를 바탕으로 복원했으므로 일부 날짜와 세부 순서는 실제 작업 시각과 다를 수 있다.

---

## 프로젝트 기본 정보

- 프로젝트명: HYB Opportunity AI
- 프로젝트 오너: Yubin Heo
- AI 기술 파트너: ChatGPT
- 개발 시작 시기: 2026년 7월
- 현재 단계: Foundation 완료 후 기능 개발
- 현재 버전: v0.2.0 개발 단계
- 현재 작업: 금액 계산의 `float` → `Decimal` 전환
- 마지막 확인 테스트: `75 passed`

---

## 프로젝트의 시작

사용자는 온라인에서 저렴하게 판매되는 상품을 AI가 수집하고, 시장 가격과 비용을 비교해 판매 기회를 찾아주는 시스템을 만들고자 했다.

초기 구상은 다음과 같았다.

1. 여러 온라인 마켓의 상품을 수집한다.
2. 동일하거나 유사한 상품의 가격을 비교한다.
3. 매입가, 배송비, 수수료 등을 반영해 예상 수익을 계산한다.
4. 수익성과 위험도를 기준으로 좋은 상품을 선별한다.
5. 장기적으로 AI가 사람이 확인하기 전에 기회를 발견하고 추천한다.

프로젝트 논의를 거치면서 목표는 단순 가격 비교 도구에서 다음 방향으로 발전했다.

> **AI 기반 Opportunity Discovery Platform**

장기적으로 다룰 영역:

- 상품 수집
- 상품 정규화
- 유사 상품 비교
- 비용 및 수익 계산
- ROI 분석
- 위험 평가
- Opportunity Score
- AI 추천
- API와 Dashboard
- 반복 업무 자동화

---

# 개발 연대기

## Phase 0 — 아이디어 및 가능성 검토

### 시기
2026년 7월 초

### 논의한 내용

- 미국과 한국 시장 모두에서 사용할 수 있는가
- eBay, Temu 등의 상품 데이터를 가져올 수 있는가
- 실시간 검색 결과를 화면에 표시할 수 있는가
- 검색 상품을 DB에 저장하고 다시 조회할 수 있는가
- 앱 형태가 더 적합한가
- 개인이 혼자 개발할 수 있는 범위인가
- 완성 후 자동화와 수익화 가능성이 있는가

### 판단

이 프로젝트는 단순 크롤러가 아니라 다음 요소가 결합된 장기 프로젝트라고 판단했다.

- 데이터 수집과 정제
- 상품 매칭
- 수익 계산
- 마켓별 연동
- 데이터베이스
- 백엔드 API
- 사용자 화면
- AI 분석
- 운영 안정성

성공을 보장하지는 않되, 작은 기능 단위로 안정적인 기반부터 구축하면 성공 가능성을 높일 수 있다는 방향으로 합의했다.

---

## Phase 1 — 초기 프로토타입과 시행착오

### 목표

상품 검색 → 목록 표시 → DB 저장 → 저장 상품 조회의 기본 흐름을 확인한다.

### 시도한 작업

- VS Code와 Python 개발 환경 구성
- eBay 상품 수집 시도
- Temu 관련 수집 또는 브라우저 동작 시도
- 검색 결과 목록
- DB 저장
- 저장 상품 조회 화면

### 발생한 문제

- 검색창이 동작하지 않음
- 검색 결과가 0개로 표시됨
- DB 상품 보기 화면에서만 목록이 보임
- 스크롤바가 동작하지 않음
- Temu 창이 하얀 화면에서 멈춤
- eBay 연동이 안정적이지 않음
- 여러 파일에 수정이 흩어져 전체 구조를 파악하기 어려움
- 컴퓨터 재부팅 후 프로젝트를 다시 실행하는 과정이 익숙하지 않음

### 이 시기에 정해진 사용자 선호

부분 코드보다 교체 가능한 **파일 전체 코드**를 제공한다.

### 결정

특정 마켓의 오류를 임시로 반복 수정하기보다, 여러 Marketplace를 수용할 수 있는 공통 기반을 먼저 만드는 편이 낫다고 판단했다.

초기 프로토타입은 가능성을 확인했지만, 장기 유지보수에 적합한 구조로 정리할 필요가 있었다.

---

## Phase 2 — Git과 GitHub 기반 구축

### 시기
2026년 7월 21일 전후

### 목표

프로젝트가 한 컴퓨터와 한 채팅에 종속되지 않도록 한다.

### 진행한 작업

- Git 기본 흐름 학습
- GitHub 저장소 구성
- 로컬 프로젝트와 원격 저장소 연결
- Commit과 Push
- 다른 컴퓨터에서 프로젝트를 다시 받는 방법 확인
- VS Code에서 기존 프로젝트를 이어가는 방법 확인

### 의미

프로젝트가 단순 로컬 폴더에서 장기 관리 가능한 소프트웨어 프로젝트로 전환됐다.

- 변경 이력 추적
- 이전 상태 복구 가능
- 다른 컴퓨터에서 작업 가능
- 새로운 채팅에서도 동일한 코드 기준 공유
- 장기적인 버전 관리 가능

---

## Phase 3 — Foundation v0.1.0

### 시기
2026년 7월 21일~22일

### 목표

기능을 계속 추가하기 전에 기본 구조와 품질 기준을 확립한다.

### 완료한 작업

- 프로젝트 구조 정리
- 모델과 핵심 도메인 구조 정리
- 테스트 환경 구축
- Code Audit
- 기본 문서 작성
- GitHub Push
- Foundation 범위 검토

### 결과

```text
Foundation v0.1.0 완료
pytest: 75 passed
```

### 확립된 개발 원칙

- 기능 추가 전 필요성과 영향을 검토한다.
- 한 번에 하나의 기능만 완성한다.
- 기존 테스트를 유지한다.
- 승인 없는 대규모 리팩토링은 하지 않는다.
- 불필요한 추상화와 디자인 패턴을 피한다.
- 기존 프로젝트 스타일을 유지한다.
- 속도를 위해 품질을 희생하지 않는다.

### 판단 우선순위

1. 정확성
2. 안정성
3. 유지보수성
4. 확장성
5. 가독성
6. 성능
7. 개발 속도

---

## Phase 4 — 프로젝트 비전 재정의

### 기존 관점

- 저렴한 상품 검색 프로그램
- 가격 비교 도구
- 온라인 차익 분석 도구

### 발전된 관점

> AI가 데이터, 비용, 위험을 종합해 사업 기회를 발견하고 우선순위를 추천하는 플랫폼

### 목표 흐름

```text
Marketplace Data
        ↓
Product Normalization
        ↓
Price Comparison
        ↓
Cost / Fee / Shipping Calculation
        ↓
Profitability Analysis
        ↓
Risk Analysis
        ↓
Opportunity Scoring
        ↓
AI Recommendation
        ↓
API / Dashboard / Automation
```

### 전략적 판단

경쟁력은 상품을 많이 가져오는 데만 있지 않다.

핵심은 다음과 같다.

- 서로 다른 마켓의 상품을 비교 가능한 형태로 정규화
- 정확한 비용 계산
- 잘못된 기회를 걸러내는 위험 분석
- 사용자가 실제 행동할 수 있는 추천
- 추천 근거를 설명할 수 있는 구조

---

## Phase 5 — v0.2.0 로드맵 결정

Foundation 완료 후 다음 순서로 진행하기로 했다.

1. Decimal Migration
2. Marketplace Architecture
3. FastAPI
4. Dashboard
5. AI Recommendation 고도화

### 순서의 이유

- Decimal: 모든 수익 계산의 정확도 기반
- Marketplace Architecture: 여러 마켓을 확장할 수 있는 구조
- FastAPI: 계산과 수집 기능을 외부 UI와 연결
- Dashboard: 검색 결과와 Opportunity 관리
- AI Recommendation: 안정적인 데이터와 계산 위에서 추천 품질 개선

### 추가 결정

기반 문서가 충분한 시점부터는 문서 확장보다 실제 구현을 우선한다.

> 문서 작성 자체를 개발 진척으로 착각하지 않는다.

---

## Phase 6 — Decimal Migration 시작

### 목표

금액과 수익 계산에 사용되는 `float`를 `Decimal`로 전환한다.

### 이유

`float`는 금액 계산에서 미세한 부동소수점 오차가 발생할 수 있다.

정확성이 필요한 값:

- 상품 가격
- 배송비
- 마켓 수수료
- 예상 판매가
- 총비용
- 순이익
- ROI 계산에 들어가는 금액

### 첫 검토 파일

```text
app/models/product.py
```

### 기존 구조

```python
price: float
shipping_cost: float
```

```python
self.price = float(price)
self.shipping_cost = float(shipping_cost)
```

```python
@property
def total_cost(self) -> float:
    return round(self.price + self.shipping_cost, 2)
```

### 변경 방향

```python
from decimal import Decimal
```

```python
price: Decimal
shipping_cost: Decimal
```

기존 입력 호환성을 고려한 입력 타입:

```python
price: Decimal | float | str
shipping_cost: Decimal | float | str = Decimal("0")
```

변환 방식:

```python
self.price = Decimal(str(price))
self.shipping_cost = Decimal(str(shipping_cost))
```

### 중요한 판단

`Decimal(float_value)` 대신 `Decimal(str(float_value))`를 사용한다.

기존 float의 내부 오차를 Decimal에 그대로 옮기는 위험을 줄이기 위해서다.

### total_cost 원칙

내부 계산 중에는 불필요한 `round()`를 하지 않는다.

```python
@property
def total_cost(self) -> Decimal:
    return self.price + self.shipping_cost
```

반올림은 다음 경계에서 처리한다.

- 화면 표시
- API 응답
- 통화 단위 확정
- 결제·정산 규칙 적용

### Decimal로 변경하지 않는 값

```python
rating: float | None
```

평점은 화폐 값이 아니므로 대상에서 제외한다.

### 예정 작업

1. 금액에 사용되는 모든 float 검색
2. Product 모델 변경
3. Marketplace Adapter 변경
4. Opportunity Engine 변경
5. 테스트 수정 및 추가
6. 전체 pytest
7. Commit
8. Push

---

## Phase 7 — 프로젝트 기억 체계 구축

### 문제

채팅이 길어지면서 느려졌고 새 채팅으로 이동해야 했다.

사용자는 새 채팅에서도 다음이 이어지기를 원했다.

- 프로젝트 방향
- 지금까지의 의사결정
- 현재 작업 상태
- AI의 협업 방식
- 성공 가능성에 대한 현실적인 관점
- 프로젝트 관리자이자 기술 파트너 역할

### 해결책

프로젝트 저장소에 기억 문서를 둔다.

#### `PROJECT_CONTEXT.md`

현재 상태를 기록한다.

- 프로젝트 목표
- 현재 버전
- 완료 작업
- 현재 작업
- 로드맵
- 개발 규칙
- 코드 제공 방식
- Git 정책

#### `AI_CHARTER.md`

AI의 역할과 협업 태도를 정의한다.

- 공동 개발자
- 프로젝트 관리자
- 시스템 아키텍트
- 코드 리뷰어
- 기술 멘토
- 품질 관리자
- 장기 전략 파트너

핵심 원칙:

- 무조건 동의하지 않는다.
- 더 나은 방법이 있으면 근거와 함께 제안한다.
- 위험한 선택은 정중하게 반대한다.
- 사용자는 Product Owner이자 최종 의사결정권자다.
- 성공을 보장하지 않되 성공 가능성을 높이는 방향으로 판단한다.

#### `DEV_LOG.md`

무엇을 했는지뿐 아니라 **왜 그렇게 했는지**를 시간순으로 기록한다.

---

## Phase 8 — AI Partnership Charter 확정

### 관계 정의

- 사용자는 Product Owner이며 최종 의사결정권자다.
- AI는 사용자의 결정을 대신하지 않는다.
- AI는 판단 근거, 대안, 위험, 우선순위를 제공한다.
- AI는 단순 코드 생성기가 아니다.
- 프로젝트에 불리한 선택에는 근거를 들어 반대 의견을 제시한다.

### Challenge Principle

좋은 기술 파트너는 항상 “네”라고 하는 사람이 아니다.

AI는 다음 상황에서 적극적으로 의견을 제시한다.

- 더 우선해야 할 문제가 있을 때
- 기존 기능을 깨뜨릴 위험이 있을 때
- 장기 유지가 어려운 구조일 때
- 더 단순하고 안전한 대안이 있을 때
- 불필요한 리팩토링이나 기술 도입이 예상될 때
- 사용자의 시간과 비용이 비효율적으로 쓰일 때

모든 반대 의견은 다음을 지킨다.

- 사용자를 존중한다.
- 객관적인 기술 근거를 제시한다.
- 가능한 대안을 함께 제시한다.
- 최종 선택은 사용자에게 맡긴다.

---

# 주요 의사결정 기록

## ADR-001 — 특정 Marketplace보다 공통 기반을 먼저 구축한다

### 배경

eBay와 Temu 연동 과정에서 수집 실패와 화면 문제에 많은 시간이 사용됐다.

### 결정

특정 마켓의 임시 해결책보다 여러 Marketplace를 수용할 수 있는 공통 구조를 먼저 만든다.

### 기대 효과

- 신규 마켓 추가 비용 감소
- 마켓별 코드 격리
- 테스트 용이성 향상
- 한 플랫폼의 장애가 전체 시스템에 미치는 영향 축소

---

## ADR-002 — Foundation 완료 후 구현으로 이동한다

### 배경

문서와 구조를 계속 다듬으면 실제 사용자 가치가 늦어질 수 있다.

### 결정

Foundation v0.1.0과 테스트 기반을 확보한 뒤에는 핵심 기능 구현을 우선한다.

---

## ADR-003 — 금액 계산에는 Decimal을 사용한다

### 결정

화폐 관련 값은 `Decimal`로 통일한다.

### 제외

평점이나 머신러닝 계산 등 float가 더 적절한 값은 의미에 따라 유지한다.

모든 float를 기계적으로 Decimal로 바꾸지는 않는다.

---

## ADR-004 — 내부 계산과 표시용 반올림을 분리한다

### 결정

내부 계산은 정밀도를 유지하고 화면과 외부 인터페이스 경계에서 통화 규칙에 맞게 반올림한다.

---

## ADR-005 — 코드는 파일 전체 형태로 제공한다

### 이유

부분 코드만 제공하면 삽입 위치나 누락으로 오류가 발생할 가능성이 높다.

### 원칙

- 파일 경로 명시
- 수정 파일 전체 제공
- 기존 기능 임의 삭제 금지
- 적용 순서와 테스트 방법 안내

---

## ADR-006 — 한 번에 하나의 기능을 완성한다

```text
계획
→ 영향 확인
→ 구현
→ 테스트
→ 검토
→ Commit
→ Push
→ 다음 기능
```

---

## ADR-007 — 프로젝트 기억은 저장소 안에 둔다

관리 문서:

- `PROJECT_CONTEXT.md`
- `AI_CHARTER.md`
- `DEV_LOG.md`

프로젝트 연속성을 특정 대화창에 의존하지 않는다.

---

# 지금까지 배운 점

## 기술

- Git은 프로젝트 시작부터 쓰는 것이 좋다.
- 마켓 연동 전에 공통 도메인 구조가 필요하다.
- 금액 계산은 데이터 타입 선택부터 중요하다.
- UI 문제처럼 보여도 데이터 흐름 문제가 원인일 수 있다.
- 전체 테스트 통과 상태는 다음 변경을 위한 안전망이다.
- 내부 계산과 표시 반올림은 분리해야 한다.
- 새로운 기술은 유행이 아니라 필요성을 기준으로 도입한다.

## 프로젝트 관리

- 많은 기능을 빨리 만드는 것이 항상 빠른 길은 아니다.
- 작업 범위를 작게 유지하면 오류와 피로가 줄어든다.
- 결정 이유를 기록하지 않으면 같은 논의를 반복한다.
- 현재 상태와 역사 기록은 별도 문서로 관리한다.
- 기술적 성공과 사업적 성공은 별도로 검증해야 한다.
- 성공 가능성은 좋은 의사결정의 반복으로 높아진다.

## 협업

- 사용자는 최종 의사결정권자다.
- AI가 무조건 동의하면 중요한 위험을 놓칠 수 있다.
- 반대 의견에는 존중, 근거, 대안이 필요하다.
- 사용자는 코딩 중 간결한 진행 안내를 선호한다.
- 깊은 기술 설명은 사용자가 요청할 때 제공한다.

---

# 현재 상태

## 완료

- 프로젝트 아이디어 구체화
- 초기 프로토타입
- Git 및 GitHub 기반
- 프로젝트 구조 정리
- Foundation v0.1.0
- Code Audit
- 기본 문서화
- 테스트 기반
- GitHub Push
- PROJECT_CONTEXT 설계
- AI_CHARTER 설계
- DEV_LOG 도입

## 마지막 확인 테스트

```text
75 passed
```

## 현재 버전

```text
v0.2.0 — Development
```

## 현재 작업

```text
Decimal Migration
```

## 현재 검토 파일

```text
app/models/product.py
```

## 다음 작업

1. Product 모델 Decimal 전환
2. 금액 관련 float 전체 검색
3. Marketplace Adapter 전환
4. Opportunity Engine 전환
5. 테스트 수정 및 추가
6. 전체 pytest
7. Commit 및 Push
8. Marketplace Architecture

---

# 로드맵

## v0.2.x — Financial Accuracy

- Decimal Migration
- 통화 반올림 정책
- 수익 계산 검증
- ROI 계산 검증
- 경계값 테스트

## v0.3.x — Marketplace Architecture

- Marketplace Protocol 또는 공통 인터페이스
- 마켓별 Adapter
- 공통 Product 변환
- 실패 처리
- 재시도 정책
- Fake Marketplace

## v0.4.x — API Layer

- FastAPI
- 검색 API
- 상품 조회 API
- Opportunity 조회 API
- 입력 검증
- 오류 응답 규칙

## v0.5.x — Dashboard

- 검색
- 결과 목록
- 상품 상세
- 수익성 표시
- Opportunity 우선순위
- 필터와 정렬

## 이후

- AI 상품 매칭
- 위험도 분석
- Opportunity Score 고도화
- 추천 이유 설명
- 알림과 자동화
- 실제 사업성 검증

---

# 새 채팅 인수인계 순서

새 채팅의 AI는 다음 순서로 확인한다.

1. `AI_CHARTER.md`
2. `PROJECT_CONTEXT.md`
3. `DEV_LOG.md`
4. 최신 코드
5. 최근 Git Commit
6. 최신 pytest 결과

그 후 간단히 정리한다.

- 현재 버전
- 마지막 완료 작업
- 현재 작업
- 테스트 상태
- 오늘 수행할 핵심 목표 한 가지

---

# 앞으로의 개발일지 작성 양식

```markdown
## YYYY-MM-DD — 작업 제목

### 오늘의 목표

### 완료한 작업

### 수정한 파일

### 테스트 결과

### 발생한 문제

### 해결 방법

### 주요 의사결정

### 남은 위험 또는 확인 사항

### 다음 작업

### Git
- Branch:
- Commit:
- Push:
```

## 기록 원칙

- 완료하지 않은 작업을 완료로 쓰지 않는다.
- 테스트하지 않은 내용은 테스트 완료로 기록하지 않는다.
- 사실과 추측을 구분한다.
- 중요한 구조 변경은 이유를 남긴다.
- 실패와 시행착오도 삭제하지 않는다.
- Commit Hash가 확인되면 기록한다.
- 문서가 커지면 버전 또는 연도별로 분리한다.

---

# 첫 공식 개발일지 기준점

이 문서 작성 시점을 HYB Opportunity AI의 첫 공식 개발일지 기준점으로 삼는다.

이전 내용은 대화와 프로젝트 맥락을 바탕으로 복원한 역사 기록이다.

이후부터는 각 개발 세션 종료 시 실제 작업 결과를 기준으로 계속 추가한다.

---

# 프로젝트 철학

좋은 Opportunity를 발견하려면 좋은 데이터가 필요하다.

좋은 데이터를 활용하려면 정확한 계산이 필요하다.

정확한 계산을 서비스로 만들려면 안정적인 구조가 필요하다.

안정적인 구조를 오래 유지하려면 테스트, 기록, 일관된 의사결정이 필요하다.

> 정확성 없는 속도보다 검증 가능한 진전을 선택한다.

> 기능 개수보다 실제로 신뢰할 수 있는 기능을 만든다.

> AI가 결정을 대신하는 것이 아니라 사용자가 더 좋은 결정을 내리도록 돕는다.

> 우리는 코드를 만드는 것이 아니라 오래 살아남는 제품을 만든다.


---

# 새 형식으로 이어지는 공식 개발일지

## 2026-07-23 — 핵심 분석 엔진 체계 완성과 AI Analyst 설계

### 오늘의 목표

기존 분석 엔진의 결과를 하나의 최종 AI 분석 보고서로 통합할 수 있도록 AI Analyst의 책임과 인터페이스를 설계한다.

### 시작 전 상태

다음 계층이 이미 구축되어 있었다.

```text
Search
→ Matching
→ Price Intelligence
→ Confidence
→ Trend
→ Opportunity
→ Explainable Score
→ Recommendation
→ Decision Report
→ Score Formatter
→ Market Analyzer
```

완료된 주요 기능:

- Product 모델 통합
- Opportunity Engine
- Explainable Score Engine
- Recommendation Engine
- Decision Report
- Score Formatter
- Market Analyzer

각 기능은 단계별 테스트 후 통합되었다.

### 완료한 작업

- AI Analyst가 사용할 기존 분석 결과를 정리했다.
- AI Analyst의 책임을 presentation layer로 제한했다.
- 최종 보고서가 제공할 필드 초안을 정했다.
- 테스트 우선 구현 순서를 확정했다.
- 개발일지와 새 채팅 인수인계 문서의 역할을 분리하기로 했다.

### 주요 설계 결정

AI Analyst는 새로운 사업 판단이나 점수 계산을 하지 않는다.

다음 결과만 조합한다.

- Recommendation
- Decision Report
- Market Analyzer
- Explainable Score

핵심 원칙:

```text
기존 엔진이 판단한다.
AI Analyst는 판단 결과를 조합하고 설명한다.
```

예정된 출력 필드:

- `overall_rating`
- `overall_score`
- `success_probability`
- `market_condition`
- `entry_difficulty`
- `buy_timing`
- `summary`
- `strengths`
- `weaknesses`
- `reason_breakdown`
- `action_plan`
- `conclusion`

### 프로젝트에 미친 의미

HYB는 단순히 상품을 찾고 점수를 계산하는 프로그램에서, 사용자가 실제 결정을 내릴 수 있도록 여러 분석을 하나의 이해 가능한 보고서로 제공하는 **AI Product Analyst**로 성장하고 있다.

이번 결정은 새로운 기능을 무작정 추가하는 대신, 기존 엔진의 책임을 보존하면서 최종 사용자 경험을 완성하는 단계라는 의미가 있다.

### 마일스톤

> **MILESTONE #6 — AI Analyst 통합 계층 설계 시작**  
> 상태: 진행 중

### 오늘의 한 줄

> 좋은 AI는 여러 계산 결과를 하나의 이해 가능한 판단으로 연결한다.

### Lessons Learned

- 최종 보고서 계층에서 점수를 다시 계산하면 책임이 중복된다.
- AI처럼 보이는 문장보다 일관된 근거 구조가 먼저다.
- 같은 계산은 한 곳에서만 수행해야 결과의 신뢰성을 유지할 수 있다.
- 계산 로직과 표현 로직을 분리하면 API, Dashboard, PDF 등으로 확장하기 쉬워진다.

### 다음 목표

```text
tests/test_ai_analyst.py
→ 실패 테스트 확인
→ engine/ai_analyst.py
→ 전체 테스트
→ orchestrator 연결
→ Commit
→ Push
```

---

## 2026-07-23 — 프로젝트 기록 체계 개편

### 오늘의 목표

채팅이 길어져 새로운 채팅으로 이동하더라도 프로젝트의 방향, 현재 상태, 협업 방식이 끊기지 않는 문서 체계를 만든다.

### 발생한 문제

기존 `DEV_LOG.md`에는 다음 내용이 한 문서에 함께 들어 있었다.

- 프로젝트 역사
- 기술 상태
- ADR
- 로드맵
- 현재 작업
- 협업 원칙
- 개발일지

초기에는 유용했지만 프로젝트가 커질수록 문서가 지나치게 커지고, 현재 상태와 역사 기록이 섞일 가능성이 있었다.

### 결정

문서의 역할을 다음처럼 분리한다.

#### `AI_CHARTER.md`

프로젝트 철학과 AI 협업 원칙을 유지한다. 이미 존재하는 문서이므로 새로 만들지 않는다.

#### `PROJECT_CONTEXT.md`

새로운 채팅에서 가장 먼저 확인하는 인수인계 문서다.

기록 항목:

- 현재 버전
- 완료 기능
- 현재 작업
- 다음 작업
- 테스트 상태
- 아키텍처
- 주의사항

#### `DEV_LOG.md`

기술 중심의 작업 기록을 담당한다.

기록 항목:

- 수정 파일
- 테스트 결과
- 발생한 오류
- 해결 방법
- ADR
- Git Commit과 Push

#### `HYB_Development_Journal.md`

사람이 읽는 프로젝트 역사다.

기록 항목:

- 프로젝트가 왜 시작되었는가
- 어떤 시행착오가 있었는가
- 왜 방향이 바뀌었는가
- 주요 마일스톤
- 오늘의 한 줄
- Lessons Learned

### 프로젝트에 미친 의미

프로젝트의 연속성을 특정 채팅창의 기억에 의존하지 않게 되었다.

새로운 채팅에서는 다음 순서로 맥락을 복원한다.

```text
AI_CHARTER.md
→ PROJECT_CONTEXT.md
→ 최신 DEV_LOG.md
→ HYB_Development_Journal.md
→ 최신 코드
→ 최근 Git Commit
→ 최신 pytest 결과
```

### 오늘의 한 줄

> 오래가는 프로젝트는 코드뿐 아니라 판단의 이유도 저장한다.

### Lessons Learned

- 현재 상태와 프로젝트 역사는 서로 다른 문서가 담당해야 한다.
- 문서는 많을수록 좋은 것이 아니라 역할이 명확할수록 좋다.
- 채팅은 협업 공간이지만 저장소 문서가 프로젝트 기억의 기준이 되어야 한다.
- 기술적 사실과 프로젝트의 이야기를 분리하면 사람과 AI 모두 더 빠르게 맥락을 이해할 수 있다.

### 다음 목표

AI Analyst 개발이 완료되는 시점에 다음 문서를 함께 갱신한다.

- `PROJECT_CONTEXT.md`
- `DEV_LOG.md`
- `HYB_Development_Journal.md`
- Roadmap 및 Milestone 상태

---

# 현재 마일스톤 요약

| 번호 | 마일스톤 | 상태 |
|---|---|---|
| 1 | 초기 프로토타입으로 가능성 확인 | 완료 |
| 2 | Git/GitHub 기반 구축 | 완료 |
| 3 | Foundation v0.1.0 | 완료 |
| 4 | Opportunity Discovery Platform 비전 확립 | 완료 |
| 5 | 핵심 분석 엔진 체계 구축 | 완료 |
| 6 | AI Product Analyst 방향 확립 | 완료 |
| 7 | AI Analyst 통합 계층 | 진행 중 |
| 8 | 프로젝트 기억 및 인수인계 체계 개편 | 완료 |

---

# 앞으로 사용할 개발일지 양식

```markdown
## YYYY-MM-DD — 작업 제목

### 오늘의 목표

### 시작 전 상태

### 완료한 작업

### 발생한 문제

### 해결 과정

### 주요 의사결정

### 결과와 검증
- 수정 파일:
- 테스트:
- Git:

### 프로젝트에 미친 의미

### 오늘의 한 줄

### Lessons Learned

### 다음 목표
```

## 기록 원칙

- 완료하지 않은 작업을 완료로 쓰지 않는다.
- 실행하지 않은 테스트를 통과했다고 기록하지 않는다.
- 사실과 추측을 구분한다.
- 실패와 시행착오를 삭제하지 않는다.
- 중요한 구조 변경은 이유를 남긴다.
- Commit hash를 확인하면 함께 기록한다.
- 현재 상태는 `PROJECT_CONTEXT.md`를 기준으로 한다.
- 개발 철학과 협업 방식은 `AI_CHARTER.md`를 기준으로 한다.
- 이 문서는 역사와 의미를 기록하며 기술 상태 문서를 불필요하게 반복하지 않는다.

---

# 프로젝트의 현재 한 줄

> HYB는 저렴한 상품을 찾는 프로그램에서 시작해, 데이터와 시장을 분석하고 그 판단 이유와 다음 행동까지 설명하는 AI Product Analyst로 성장하고 있다.
