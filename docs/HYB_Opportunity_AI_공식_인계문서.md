# HYB Opportunity AI — 공식 프로젝트 인계 문서

## 0. 사용 방법

이 문서는 새 ChatGPT 채팅에서 HYB Opportunity AI 프로젝트를 그대로 이어가기 위한 공식 인계 문서다.

새 채팅을 시작할 때 이 문서 전체를 붙여넣고, 마지막에 아래 문장을 추가한다.

> 이 인계 문서를 기준으로 HYB Opportunity AI 프로젝트를 이어가자. 먼저 현재 상태를 요약하고, 다음 단계인 FastAPI Web Dashboard Phase 1부터 진행해줘.

---

# 1. 프로젝트 정체성

## 프로젝트명

HYB Opportunity AI

## 프로젝트 목표

온라인 마켓플레이스의 상품 데이터를 수집하고, 유사 상품을 그룹화한 뒤, 수익성·ROI·가격 정보·시장 경쟁·위험도 등을 분석하여 수익 기회를 자동으로 찾아주는 AI 기반 Commerce Opportunity Platform을 구축한다.

단기 목표는 다음과 같다.

- 상품 검색
- 유사 상품 그룹화
- 예상 판매가 계산
- 순이익 및 ROI 계산
- 기회 점수 산출
- AI 추천
- AI Partner 보고서
- 분석 기록 저장
- CLI 및 Web Dashboard 제공

장기 목표는 다음과 같다.

- 실제 Production Marketplace 데이터 사용
- 해외→해외 상품 기회 탐색
- 여러 마켓 간 가격 차이 분석
- Opportunity 자동 수집
- 분석 기록 기반 AI Memory 강화
- 자동 알림 및 후보 관리
- 운영 가능한 HYB AI Commerce 플랫폼 구축

---

# 2. 사용자 성향 및 작업 원칙

사용자는 코딩 초보이며 Windows와 VS Code를 사용한다.

코드 수정 안내 시 반드시 다음 원칙을 따른다.

1. 부분 수정이나 일부 코드 조각보다 파일 전체 코드를 제공한다.
2. 파일 경로를 먼저 명확히 적는다.
3. “기존 내용을 전부 지우고 아래 코드로 교체” 방식으로 안내한다.
4. 한 번에 너무 많은 파일을 수정하지 않는다.
5. 각 단계가 끝날 때 반드시 `python -m pytest`로 검증한다.
6. 테스트 통과 개수를 기준점으로 기록한다.
7. 에러가 발생하면 추측으로 코드를 계속 추가하지 말고 실제 파일 내용과 오류 로그를 먼저 확인한다.
8. 프로젝트 구조와 기존 인터페이스를 함부로 추정하지 않는다.
9. 기능 구현보다 구조 안정성과 회귀 방지를 우선한다.
10. 사용자가 따라오기 쉽게 명령어를 PowerShell 기준으로 제공한다.

사용자는 HYB 프로젝트를 최우선 프로젝트로 생각하고 있으며, 단순한 코딩 도우미보다 함께 성공 가능성을 검토하고 방향을 관리하는 AI 파트너를 원한다.

AI 파트너는 무조건 긍정적으로만 말하지 말고 다음을 구분해서 설명해야 한다.

- 실제 완료된 것
- 테스트로 확인된 것
- 아직 검증되지 않은 것
- 사업적으로 위험한 것
- 다음 우선순위

---

# 3. 현재 개발 상태

현재 전체 테스트 결과:

```text
120 passed
```

이 숫자는 새 기능을 구현할 때 기준선이다.

새로운 변경 후 기존 테스트가 깨지면 기능 추가보다 회귀 원인을 먼저 해결한다.

---

# 4. 현재 완성된 기능

## Core Architecture

- 설정 관리
- Marketplace 분리
- Engine 분리
- Storage 분리
- App/CLI 분리
- Presentation Layer 분리

## Marketplace Search

- eBay Sandbox 연동 경험
- Browse API 기반 상품 검색
- 여러 Marketplace 검색을 수용하는 구조
- 검색 실패 핸들러 지원

단, 실제 Production Marketplace 데이터 검증은 아직 완료되지 않았다.

## Product Grouping

- 유사 상품 비교
- 상품 그룹화
- 그룹 내 대표 상품 및 유사 상품 수 관리

## Opportunity Analysis

- 예상 판매가
- 매입가
- 배송비
- 수수료
- 순이익
- ROI
- 기본 Opportunity Score
- Adjusted Opportunity Score
- Final Opportunity Score

## Price Intelligence

- 유사 상품 가격 정보
- 추천 판매가
- 가격 관련 지표
- Price Trend 연결 구조
- Trend Score 및 보정값 연결 구조

## Recommendation / Decision

- AI Recommendation
- 추천 등급
- 권장 행동
- 성공 확률
- 추천 이유
- 경고
- Decision Report

## AI Partner

`AIPartnerReport`에 다음 필드가 있다.

```python
title
summary
recommendation
next_action
memory_summary
```

OpportunityResult의 분석 내용을 사용자가 이해하기 쉬운 최종 판단과 다음 행동으로 정리한다.

## AI Memory

- 과거 분석 기록 활용 구조
- Memory Insight
- sample_size
- rank_label
- overall_percentile
- summary
- AI Partner의 memory_summary 연결

## Storage

- SQLite 기반 Opportunity History 저장
- 최근 분석 기록 조회
- CLI `--history`
- DB 경로 옵션
- `--no-save`

## CLI

현재 실행 진입점:

```python
# main.py
from app.cli import run_cli

if __name__ == "__main__":
    raise SystemExit(run_cli())
```

CLI 주요 옵션:

```text
query
--limit
--top
--selling-multiplier
--shipping-cost
--fee-rate
--monthly-sales
--competitors
--history
--db
--no-save
--risk
```

CLI는 기존의 직접 출력 구조에서 Presentation Layer를 사용하는 구조로 전환되었다.

---

# 5. 현재 핵심 아키텍처

```text
main.py
    ↓
app.cli.run_cli()
    ↓
engine.orchestrator.find_best_opportunities()
    ↓
OpportunityResult
    ↓
presentation.dashboard.build_dashboard_card(s)
    ↓
DashboardCard
    ↓
presentation.formatter
    ↓
presentation.cli
    ↓
CLI Dashboard 출력
```

계층별 역할:

```text
marketplaces/
    외부 마켓 검색 및 데이터 수집

engine/
    상품 그룹화, 가격 분석, 기회 계산, 추천, AI Partner

storage/
    SQLite 및 분석 기록 저장

presentation/
    엔진 결과를 UI 독립적인 Dashboard 모델로 변환하고 출력

app/
    프로그램 실행 흐름과 CLI 입력 처리

main.py
    CLI 실행 진입점
```

중요 원칙:

- Engine은 HTML이나 CLI 출력 형식을 알면 안 된다.
- Presentation은 Marketplace API를 직접 호출하면 안 된다.
- Web은 Engine 객체를 직접 템플릿에 넘기기보다 DashboardCard를 사용한다.
- CLI와 Web은 같은 DashboardCard 변환 로직을 재사용한다.

---

# 6. OpportunityResult 구조

현재 확인된 주요 필드:

```python
product
analysis
matched_product_count
price_intelligence
confidence
adjusted_opportunity_score
price_trend
trend_score
trend_score_adjustment
final_opportunity_score
ai_recommendation
decision_report
ai_partner_report
memory_insight
```

---

# 7. Product 주요 필드

```python
marketplace
item_id
title
price
currency
shipping_cost
total_cost
seller
url
image_url
condition
in_stock
```

`total_cost`는 일반적으로 상품 가격과 배송비를 합한 값으로 사용된다.

---

# 8. Presentation Layer

현재 생성된 파일:

```text
presentation/
    __init__.py
    models.py
    dashboard.py
    formatter.py
    cli.py
```

## models.py

다음 Dataclass가 존재한다.

```python
DashboardProduct
DashboardMetrics
DashboardRecommendation
DashboardAIPartner
DashboardMemory
DashboardCard
```

모든 모델은 `to_dict()`를 지원한다.

## dashboard.py

핵심 함수:

```python
build_dashboard_card(result: OpportunityResult) -> DashboardCard
build_dashboard_cards(results) -> list[DashboardCard]
```

역할:

```text
OpportunityResult
        ↓
DashboardCard
```

## formatter.py

핵심 함수:

```python
format_dashboard_card(card)
format_dashboard_cards(cards)
```

DashboardCard를 사람이 읽을 수 있는 텍스트로 변환한다.

빈 카드 목록은 현재 다음 문자열을 반환한다.

```text
No dashboard results.
```

## presentation/cli.py

핵심 함수:

```python
print_dashboard_result(result)
print_dashboard_results(results)
```

## app/cli.py integration

`render_results()`는 더 이상 분석 결과를 직접 포맷하지 않는다.

현재 흐름:

```python
selected_results = list(results[:top])
print_dashboard_results(selected_results, output=output)
```

---

# 9. 현재 테스트 상태

최종 기준:

```text
120 passed
```

최근 추가된 테스트 영역:

```text
tests/test_presentation_models.py
tests/test_dashboard_builder.py
tests/test_dashboard_formatter.py
tests/test_presentation_cli.py
tests/test_cli_dashboard_integration.py
tests/test_cli.py
```

CLI 테스트는 과거 깨진 한글 문자열과 구형 출력 기준을 현재 출력에 맞게 갱신했다.

현재 빈 검색 결과 관련 기준:

```text
검색어: ...
분석 결과: 0개 그룹
표시 결과: 0개
No dashboard results.
```

---

# 10. 최근 완료한 작업

## Dashboard Models

완료 후 테스트:

```text
106 passed
```

## Dashboard Builder

완료 후 테스트:

```text
110 passed
```

## Dashboard Formatter / Presentation CLI

완료 후 테스트:

```text
117 passed
```

## App CLI Integration

완료 후 기존 테스트 갱신:

```text
120 passed
```

따라서 현재 코드는 CLI가 실제로 Presentation Layer를 사용하는 상태다.

---

# 11. 현재 requirements.txt

현재 확인된 내용:

```text
pytest>=8.0,<9.0
requests>=2.32,<3.0
python-dotenv>=1.0,<2.0
```

FastAPI는 아직 설치하거나 추가하지 않았다.

Web Dashboard 구현 시 예상 추가 항목:

```text
fastapi
uvicorn
jinja2
python-multipart
```

`python-multipart`는 HTML Form 방식으로 검색 요청을 받을 경우 필요할 수 있다.

버전 범위는 실제 설치 가능한 최신 호환 버전을 확인한 뒤 지정한다.

---

# 12. 다음 개발 단계

다음 작업은 FastAPI Web Dashboard Phase 1이다.

## 1차 목표

```text
브라우저 접속
    ↓
HYB Dashboard 기본 화면
    ↓
검색어 및 분석 옵션 입력
    ↓
기존 find_best_opportunities() 호출
    ↓
DashboardCard 변환
    ↓
HTML 상품 카드 표시
```

## 권장 신규 구조

```text
web/
    __init__.py
    app.py
    schemas.py
    services.py
    templates/
        dashboard.html
    static/
        dashboard.css
```

단, 코드를 작성하기 전에 현재 전체 프로젝트 트리와 관련 인터페이스를 다시 확인하는 것이 안전하다.

권장 확인 명령:

```powershell
tree /F
```

또는 너무 길 경우:

```powershell
Get-ChildItem -Recurse -File |
    Where-Object {
        $_.FullName -notmatch "\\.venv\\|__pycache__|\.git"
    } |
    Select-Object FullName
```

Orchestrator 함수의 전체 시그니처도 다시 확인한다.

```powershell
Select-String `
    -Path engine\orchestrator.py `
    -Pattern "def find_best_opportunities" `
    -Context 5,120
```

---

# 13. FastAPI 구현 원칙

1. 기존 Engine 코드를 수정하지 않는다.
2. Web 전용 서비스 계층에서 `find_best_opportunities()`를 호출한다.
3. 결과를 `build_dashboard_cards()`로 변환한다.
4. 템플릿에는 가능하면 `DashboardCard.to_dict()` 결과를 전달한다.
5. 검색 실패는 전체 페이지 오류가 아니라 사용자에게 경고로 보여준다.
6. DB 저장 여부를 명확히 제어한다.
7. 검색 중 예외를 숨기지 않는다.
8. 초기 Web 단계에서는 JavaScript 프레임워크를 도입하지 않는다.
9. Jinja2 + CSS로 최소 기능부터 완성한다.
10. 신규 Web 코드에 테스트를 추가한다.
11. 변경 후 목표 테스트 수를 계산하고 전체 테스트를 실행한다.

---

# 14. FastAPI Phase 1 권장 구현 순서

## Step 1

requirements.txt에 필요한 의존성 추가

## Step 2

Web 앱 생성 및 `/health` 테스트

예상:

```text
GET /health
→ {"status": "ok"}
```

## Step 3

`GET /` 기본 Dashboard 화면

## Step 4

Web Search Request Schema 또는 Form 처리

## Step 5

Web Service에서 Orchestrator 호출

## Step 6

OpportunityResult → DashboardCard 변환

## Step 7

Jinja2 카드 렌더링

## Step 8

검색 실패와 빈 결과 UI

## Step 9

FastAPI TestClient 기반 테스트

## Step 10

전체 테스트 후 브라우저 실행

예상 실행 명령:

```powershell
uvicorn web.app:app --reload
```

예상 주소:

```text
http://127.0.0.1:8000
```

---

# 15. 아직 검증되지 않은 부분

다음은 완료된 것으로 말하면 안 된다.

- eBay Production 완전 연동
- Amazon 실제 검색
- 실거래 기반 판매가 정확도
- 실제 구매 가능 재고 검증
- 환율 자동 반영
- 국가별 세금 및 관세
- 반품 비용
- 실제 판매 자동 등록
- 주문 자동 처리
- 자동 수익 발생
- Production 배포
- 실사용자 검증

현재 120개 테스트는 코드의 예상 동작을 검증하는 것이며, 실제 사업 수익성을 증명하는 것은 아니다.

---

# 16. 중간 감사 결과

## 강점

### 아키텍처

매우 좋음.

Engine, Storage, Presentation, App이 분리되어 있다.

### 테스트

좋음.

120 PASS 기준선이 있으며 기능 추가 때 회귀 여부를 빠르게 확인할 수 있다.

### 확장성

매우 좋음.

DashboardCard를 중심으로 CLI, Web, API, Desktop 확장이 가능하다.

### 개발 방식

좋음.

작은 단위로 구현하고 테스트를 추가하며 진행했다.

## 위험

### 실제 데이터 위험

높음.

Sandbox나 테스트 데이터에서 계산이 잘 되더라도 실제 Marketplace 데이터의 품질과 일치 여부는 별개다.

### 가격 추정 위험

중간~높음.

단순 배수나 제한된 유사 상품 가격만으로 실제 판매가를 정확히 예측하기 어렵다.

### 상품 동일성 위험

중간~높음.

모델, 용량, 상태, 잠금 여부, 색상, 구성품 차이가 수익 계산을 왜곡할 수 있다.

### 비용 누락 위험

높음.

배송, 플랫폼 수수료, 결제 수수료, 세금, 관세, 반품, 환율 변동 등이 실제 순이익을 크게 줄일 수 있다.

### 자동화 기대 위험

높음.

현재는 기회 분석 시스템이며 완전 자동 구매·판매 시스템은 아니다.

---

# 17. 현실적인 프로젝트 평가

## 기술 기반

좋음.

## 사용자 인터페이스

CLI까지 완료. Web은 시작 전.

## 실제 운영 준비

아직 부족함.

## 사업성

가능성은 있으나 Production 데이터 검증 전에는 판단을 확정할 수 없다.

## 현재 전체 진행률

“완전 자동 수익 플랫폼”을 최종 목표로 보면 약 50~60% 수준으로 보는 것이 더 보수적이고 현실적이다.

“확장 가능한 분석 엔진과 CLI MVP”를 기준으로 보면 75~85% 수준이다.

기존 대화에서 약 70%라고 평가했으나, 이 수치는 어떤 완료 기준을 쓰는지에 따라 달라진다.

---

# 18. 다음 우선순위

1. FastAPI Web Dashboard Phase 1
2. Web에서 실제 검색 흐름 검증
3. 검색 결과와 분석 값의 데이터 품질 검사
4. Production Marketplace 전환 계획
5. 실제 상품 20~50개 표본 검증
6. 비용 모델 정밀화
7. 상품 매칭 정확도 개선
8. Opportunity 후보 저장 및 상태 관리
9. 차트 및 분석 기록 UI
10. 배포와 모니터링

Web UI 구현 후에는 곧바로 화려한 기능을 늘리기보다 실제 데이터 검증으로 넘어가는 것이 중요하다.

---

# 19. 새 AI 파트너가 지켜야 할 운영 방식

새 채팅의 AI는 다음 태도를 유지한다.

- 사용자를 초보 개발자로 가정하고 순서대로 안내한다.
- 파일 전체 교체 코드를 우선 제공한다.
- 한 번에 적은 수의 파일을 변경한다.
- 실제 파일을 보지 않은 상태에서 필드나 경로를 만들어내지 않는다.
- 테스트 통과를 확인한 다음 단계로 넘어간다.
- 기존 기능을 깨뜨릴 가능성이 있으면 먼저 경고한다.
- 사업 성공 가능성과 기술 구현 성공을 혼동하지 않는다.
- 검증되지 않은 기능을 완료됐다고 표현하지 않는다.
- 사용자의 최우선 프로젝트라는 점을 고려해 개발 흐름과 우선순위를 관리한다.
- 단순히 사용자의 의견에 동의하기보다 더 안전하거나 성공 가능성이 높은 방향이 있으면 설명한다.
- 현재 상태와 다음 목표를 항상 연결해서 설명한다.

---

# 20. 새 채팅 시작용 최종 프롬프트

아래 내용을 새 채팅 첫 메시지로 사용할 수 있다.

---

나는 Windows와 VS Code를 사용하는 코딩 초보이며, HYB Opportunity AI 프로젝트를 개발 중이다.

이 프로젝트는 온라인 마켓플레이스 상품을 검색하고, 유사 상품 그룹화, 예상 판매가, 순이익, ROI, Opportunity Score, AI Recommendation, Decision Report, AI Partner, AI Memory를 통해 수익 기회를 찾는 AI Commerce 플랫폼이다.

현재 테스트는 `120 passed` 상태다.

현재 아키텍처는 다음과 같다.

```text
main.py
    ↓
app.cli
    ↓
engine.orchestrator.find_best_opportunities()
    ↓
OpportunityResult
    ↓
presentation.dashboard
    ↓
DashboardCard
    ↓
presentation.formatter / presentation.cli
    ↓
CLI Dashboard
```

Presentation Layer는 이미 완성되어 있다.

```text
presentation/
    __init__.py
    models.py
    dashboard.py
    formatter.py
    cli.py
```

현재 다음 기능이 완료되었다.

- Marketplace 검색 구조
- 유사 상품 그룹화
- 수익성 및 ROI 계산
- Opportunity Score
- Price Intelligence
- AI Recommendation
- Decision Report
- AI Partner
- AI Memory
- SQLite 분석 기록 저장
- Dashboard Models
- Dashboard Builder
- Dashboard Formatter
- CLI Dashboard
- app/cli.py 실제 연결
- 전체 테스트 120 PASS

다음 단계는 FastAPI Web Dashboard Phase 1이다.

목표:

```text
브라우저 접속
    ↓
HYB Dashboard
    ↓
검색어 입력
    ↓
find_best_opportunities()
    ↓
build_dashboard_cards()
    ↓
HTML 상품 카드 출력
```

예상 신규 구조:

```text
web/
    __init__.py
    app.py
    schemas.py
    services.py
    templates/
        dashboard.html
    static/
        dashboard.css
```

코드를 수정할 때는 반드시 파일 전체 코드를 제공해줘. 부분 교체 방식은 피하고, 파일 경로와 실행 명령을 정확히 알려줘. 한 번에 너무 많은 파일을 만들지 말고, 각 단계 후 `python -m pytest`로 확인하자.

또한 실제 파일 구조나 클래스 필드를 추측하지 말고, 필요한 경우 먼저 PowerShell 명령으로 현재 코드를 확인해줘.

이 프로젝트의 최종 목표는 실제 Production Marketplace 데이터를 기반으로 수익 기회를 자동 탐색하는 플랫폼이지만, 현재 Production 데이터와 실제 사업 수익성은 아직 검증되지 않았다. 기술적 완료와 사업적 검증을 구분해서 안내해줘.

이 인계 내용을 기준으로 먼저 현재 상태와 다음 작업을 짧게 확인한 뒤, FastAPI Web Dashboard Phase 1을 시작하자.

---

# 21. 새 채팅에서 가장 먼저 할 일

새 채팅의 AI가 곧바로 대규모 코드를 작성하지 않도록 한다.

먼저 다음을 확인한다.

```powershell
Get-Content requirements.txt
Get-Content presentation\models.py
Get-Content presentation\dashboard.py
Get-Content engine\orchestrator.py
```

`engine/orchestrator.py`가 너무 길면 `find_best_opportunities()` 부분만 확인한다.

그 후 FastAPI 최소 앱과 health check부터 진행한다.

---

# 22. 현재 체크포인트

```text
Project: HYB Opportunity AI
Phase: CLI MVP 완료 / Web Dashboard 시작 직전
Tests: 120 passed
Next: FastAPI Phase 1
Risk: Production 및 실제 수익성 미검증
```
