# HYB Architecture Alignment Report v1

## 1. 문서 목적

이 문서는 Sprint 5 시작 시점의 실제 코드베이스를 기준으로 HYB의 현재
아키텍처, 안정 영역, 전환 중인 영역, 기술 부채와 다음 확장 순서를 확정한다.

이번 리뷰의 핵심 원칙은 다음과 같다.

- 실제 코드와 기존 문서를 근거로 판단한다.
- 이미 안정적인 기능은 다시 만들지 않는다.
- 패턴을 미리 추가하지 않고 실제 변형 축이 생길 때 추상화한다.
- 기존 엔진을 한 번에 재작성하지 않고 Application Port와 Infrastructure
  Adapter를 이용해 점진적으로 전환한다.
- 코드 변경보다 경계와 책임을 먼저 확정한다.

## 2. 검토 기준

검토 대상은 다음 영역이다.

- `app/domain`
- `app/application`
- `app/infrastructure`
- `app/engine`
- 기존 루트 패키지 `engine`, `presentation`, `storage`, `market_data`,
  `marketplaces`, `services`, `collectors`
- Discovery 관련 테스트와 아키텍처 문서

이번 PR은 문서 전용 Architecture Alignment 작업이다. 런타임 동작과 공개 API는
변경하지 않는다.

## 3. 현재 아키텍처 요약

HYB는 현재 **점진적 전환형 하이브리드 아키텍처**다.

```text
Presentation / CLI
        |
        +--------------------------+
        |                          |
        v                          v
신규 Application 계층         기존 engine.orchestrator
        |                          |
        v                          v
Application Port           기존 Engine / Service / Storage
        ^
        |
Infrastructure Adapter
        |
        v
기존 엔진 및 저장소 구현
```

신규 구조는 다음 의존 방향을 목표로 한다.

```text
Presentation
    -> Application
        -> Domain

Infrastructure
    -> Application Port
    -> Domain
```

그러나 전체 코드베이스는 아직 이 구조로 완전히 이전되지 않았다. 기존
`engine`, `presentation`, `storage`, `market_data` 계층은 실제 기능을 계속
담당하며, `app/infrastructure`가 이들을 신규 Application Port에 연결한다.
이는 현재 단계에서 의도된 **Strangler Migration**으로 판단한다.

## 4. 계층별 평가

### 4.1 Domain

#### 안정 영역

- `app/domain/opportunity`
  - `OpportunityScore`, `OpportunityEvaluation`, Decision 및 Reason 계약을
    불변 도메인 모델로 분리했다.
  - 점수 객체와 최종 판단 객체의 책임이 분리되어 있다.
- `app/domain/discovery`
  - `DiscoveryResult`, Queue, Pipeline, Ranking의 책임이 명확하다.
  - Ranking은 기존 점수를 재계산하지 않고 정렬과 rank 부여만 담당한다.
- `app/domain/trend`
  - 방향과 변동성 등 순수 개념을 별도 모델로 표현한다.

#### 관찰 사항

- `app/domain/discovery.models.DiscoveryResult`는 공용 `app.models.Product`에
  의존한다. 현재 Product가 사실상 Shared Kernel이므로 허용 가능한
  과도기적 선택이다.
- `app/domain/change.detection`은 `market_data` Snapshot 타입에 직접
  의존한다. Snapshot이 장기적으로 Domain Value Object인지 Infrastructure
  DTO인지 아직 경계가 확정되지 않았다.

#### 결정

- Discovery와 Opportunity Domain은 현재 구조를 유지한다.
- Product를 별도 Discovery Candidate나 Dataset으로 복제하지 않는다.
- Change Domain과 `market_data`의 경계는 별도 PR에서 계약을 먼저 정의한 뒤
  이동 여부를 판단한다.

### 4.2 Application

#### 안정 영역

- `DiscoverOpportunitiesUseCase`
  - 입력 검증, Session 생명주기, Gateway 호출, Ranking, Statistics 조립을
    담당한다.
  - 가격, 수익, 신뢰도, 추천 계산을 직접 수행하지 않는다.
- `DiscoverOpportunitiesWorkflow`
  - Discover와 선택적 Publish 단계만 조정한다.
  - Workflow Context와 Runner를 통해 실행 기록을 남긴다.
  - Observer 실패와 비즈니스 Workflow 실패를 분리한다.
- Application Port
  - `OpportunityDiscoveryGateway`를 통해 Use Case가 Marketplace와 기존
    Orchestrator를 직접 알지 않도록 한다.

#### 관찰 사항

- `DiscoverOpportunitiesUseCase`와 `DiscoveryPipeline` 모두 RankingEngine을
  호출할 수 있다. 현재 둘은 서로 다른 진입 경로이므로 즉시 중복으로 보지
  않는다. 다만 하나의 실행 흐름에서 두 번 Ranking하지 않는다는 계약은
  유지해야 한다.
- `strong_score_threshold`는 Application 통계 정책이다. 최종 매수 판단
  정책과 혼동하지 않도록 명칭과 문서 경계를 유지해야 한다.

#### 결정

- Workflow와 Use Case는 현재 공개 API를 유지한다.
- Collect, Normalize, Match, Analyze를 문서상 가상의 Workflow Step으로 먼저
  만들지 않는다. 계약이 실제로 추출될 때만 단계화한다.
- Business Intelligence를 추가할 때 Use Case 내부에 계산 코드를 직접
  누적하지 않고 Domain/Engine 결과를 조립하는 역할만 유지한다.

### 4.3 Infrastructure

#### 안정 영역

- `OrchestratorOpportunityDiscoveryGateway`
  - 기존 `engine.orchestrator` 결과를 `DiscoveryResult`로 변환한다.
  - 신규 Application 계층이 기존 엔진 구현에 직접 결합되는 것을 막는다.
- `PriceHistorySnapshotProvider`
  - 기존 Repository와 Snapshot Mapper를 Application 계약에 연결한다.

#### 관찰 사항

- Infrastructure Adapter는 현재 전환의 핵심 경계다.
- Gateway metadata에 `analysis`, `confidence_score`,
  `success_probability`가 자유 형식으로 전달된다. 확장에는 유리하지만,
  핵심 의사결정 필드까지 metadata에 계속 추가하면 계약 안정성이 약해질 수
  있다.

#### 결정

- 기존 엔진 재작성 대신 Adapter 확장을 우선한다.
- 두 개 이상의 소비자가 동일 metadata key를 사용하게 되면 그 시점에
  Typed Contract 승격을 검토한다.
- Marketplace별 구현은 Domain으로 이동하지 않는다.

### 4.4 Presentation

#### 현재 상태

- 신규 `app/cli.py`와 기존 루트 `presentation` 패키지가 공존한다.
- 기존 Presentation은 `engine.orchestrator.OpportunityResult`에 직접
  의존한다.
- 신규 Discovery Workflow/Application Use Case는 아직 모든 CLI 경로의
  유일한 진입점이 아니다.

#### 평가

이는 즉시 결함이라기보다 마이그레이션이 완료되지 않은 상태다. 기존 CLI와
Dashboard 호환성을 유지하면서 신규 Application 진입점으로 점진적으로
전환해야 한다.

#### 결정

- 현재 CLI를 한 번에 교체하지 않는다.
- 다음 Presentation 통합 PR에서는 Dashboard가 `DiscoveryResult` 또는 별도
  Application Response DTO를 받을 수 있는 Adapter를 추가한다.
- Presentation에 새로운 사업 계산 로직을 추가하지 않는다.

### 4.5 기존 Engine 및 지원 패키지

기존 루트 `engine`은 아직 다음 핵심 기능의 실질적 구현을 보유한다.

- 상품 매칭과 정규화
- 가격 및 시장 분석
- 수익성 계산
- Confidence와 Recommendation
- AI Partner 및 Memory
- Orchestration

`app/engine`에는 새 Opportunity Score/Decision Engine이 추가되어 있다.
따라서 현재는 **기존 엔진군과 신규 엔진군이 병존**한다.

#### 결정

- 기존 엔진을 deprecated로 단정하지 않는다.
- 신규 엔진을 실제 Discovery 출력에 연결하기 전까지 기능 중복 여부를 코드와
  테스트로 비교한다.
- 새 Business Rule Engine을 별도로 만들기 전에 이미 구현된
  `app.engine.opportunity_score`와 `app.engine.opportunity_decision`의 입력
  연결 지점을 먼저 설계한다.

## 5. Discovery 실행 계약

현재 공식 Discovery 흐름은 다음과 같다.

```text
Presentation / Scheduler
        |
        v
DiscoverOpportunitiesWorkflow
        |
        v
DiscoverOpportunitiesUseCase
        |
        v
OpportunityDiscoveryGateway (Port)
        ^
        |
OrchestratorOpportunityDiscoveryGateway
        |
        v
기존 engine.orchestrator
        |
        v
DiscoveryResult 목록
        |
        v
RankingEngine
        |
        v
DiscoverOpportunitiesResponse
        |
        +--> Statistics
        +--> Optional Publisher
```

### 계약 규칙

1. Gateway는 rank가 확정되지 않은 `DiscoveryResult` 목록을 반환한다.
2. RankingEngine은 점수를 재계산하지 않는다.
3. Use Case는 Ranking 결과를 Response에 담는다.
4. Workflow는 계산하지 않고 Use Case 실행과 Publish만 조정한다.
5. Presentation은 사업 점수를 임의로 보정하지 않는다.
6. Infrastructure는 외부/기존 타입을 Domain/Application 계약으로 변환한다.

## 6. Ranking 결정

현재 Ranking 우선순위는 다음과 같다.

1. 높은 `opportunity_score`
2. 높은 `matched_product_count`
3. 낮은 `product.total_cost`
4. 상품 제목의 결정적 정렬
5. `identity_key`의 결정적 정렬

현재 구현은 짧고, 결정적이며, 단일 정책만 존재한다.

### Architecture Decision

- Sprint 5.1에서 Strategy Pattern을 도입하지 않는다.
- ROI, Risk, Marketplace 등 실제로 대체 가능한 정렬 정책이 두 개 이상 생길
  때 Strategy 추출을 재검토한다.
- 정렬 기준을 늘리기 전에 Business Score와 Ranking의 책임을 구분한다.
  Business Score는 기회의 품질을 계산하고, Ranking은 계산된 결과의 순서를
  정한다.

## 7. Dataset 계층 결정

현재 `DiscoveryRun.results`, `DiscoverOpportunitiesResponse.results`,
`DiscoveryStatistics`가 결과 컬렉션과 요약 역할을 이미 제공한다.

따라서 지금 별도의 `OpportunityDataset`을 추가하면 다음 문제가 생긴다.

- 기존 Result/Response/Run 계약과 역할 중복
- `filter`, `rank`, `export` 책임이 한 객체에 모일 위험
- 아직 존재하지 않는 대규모 배치 요구를 선행 설계하는 문제

### Architecture Decision

- Sprint 5에서 Dataset 객체를 새로 만들지 않는다.
- 실제 요구가 생기면 다음 조건을 기준으로 도입을 검토한다.
  - 페이지네이션 또는 수만 건 배치 처리
  - 영속 Dataset ID와 재현 가능한 Snapshot 필요
  - 학습/검증용 라벨과 Feature Schema 필요
  - 여러 분석 단계가 동일한 불변 Dataset을 공유해야 함

## 8. 기술 부채 및 위험도

### P1 — 다음 기능 전에 해결 또는 설계 필요

1. **신규 Opportunity Score/Decision과 Discovery 연결 부재**
   - 엔진은 구현되어 있으나 Discovery Application의 공식 결과 흐름과 아직
     통합되지 않았다.
   - 새 Business Rule을 중복 구현하기 전에 연결 계약이 필요하다.

2. **핵심 Intelligence 필드의 metadata 의존 가능성**
   - Confidence와 success probability가 metadata에 있다.
   - 다음 통합에서 어떤 값이 정식 Contract인지 결정해야 한다.

### P2 — 계획된 점진 개선

1. 기존 Presentation의 Orchestrator 직접 의존
2. Change Domain과 `market_data` Snapshot 경계
3. `app/engine`과 기존 `engine`의 명명 및 소유권 경계
4. 문서상 최신 테스트 기준과 실제 코드 상태의 동기화

### P3 — 실제 요구 발생 시 검토

1. Ranking Strategy
2. Persistent/Durable Queue
3. Opportunity Dataset
4. 비동기 Workflow 및 Retry/Outbox
5. Marketplace/Category별 정책 선택기

## 9. 절대 건드리지 않을 안정 영역

다음 영역은 구체적인 결함이나 새 요구가 확인되기 전까지 리팩터링하지 않는다.

- `RankingEngine.rank()`의 공개 API와 현재 결정적 정렬 동작
- `DiscoverOpportunitiesUseCase.execute()`의 공개 진입점
- `DiscoverOpportunitiesWorkflow.execute()`의 Discover/Publish 흐름
- `OpportunityDiscoveryGateway` Port 방향
- 기존 Orchestrator를 Adapter 뒤에서 재사용하는 전환 전략
- `OpportunityScore`와 `OpportunityEvaluation`의 책임 분리
- 기존 테스트가 보장하는 CLI와 Dashboard 호환성

## 10. Sprint 5 실행 권고

### PR-1 — Architecture Alignment

- 본 문서 작성
- 기존 동작 변경 없음
- Architecture Index와 Changelog 갱신

### PR-2 — Opportunity Intelligence Integration Contract

목표:

- 기존 `DiscoveryResult`가 가진 값과 신규 `OpportunityFactors` 입력의 매핑 가능
  여부를 확인한다.
- 부족한 데이터는 새 계산으로 추정하지 않고 명시적으로 식별한다.
- `OpportunityScoreEngine`과 `OpportunityDecisionEngine`을 연결하는 Application
  Service 또는 Adapter의 입출력 계약을 설계한다.

코드 구현 전 산출물:

- 입력 Source Map
- 필수/선택 필드
- 결측값 정책
- 기존 Recommendation과 신규 Decision의 공존/전환 정책

### PR-3 — Minimal Intelligence Integration

- PR-2 계약에서 실제로 지원되는 요소만 연결한다.
- 기존 Recommendation을 제거하지 않는다.
- 새 Evaluation을 `DiscoveryResult`의 정식 필드로 승격할지 별도 Response DTO로
  둘지 테스트와 소비자 요구를 기준으로 결정한다.

### PR-4 — Explainability Contract

- 구조화된 Reason을 Presentation 문장과 분리한다.
- 현지화와 사용자 문장은 Presentation/Application Adapter가 담당한다.

### PR-5 — Presentation Migration Slice

- 기존 Dashboard 호환성을 유지한 채 신규 Discovery Application 진입점을
  사용하는 한 개의 CLI 경로를 완성한다.

## 11. Engineering Health Check

| 항목 | 평가 | 근거 |
|---|---|---|
| Architecture | 양호 | 신규 계층과 Port/Adapter 경계가 존재함 |
| Domain Separation | 양호 | Discovery와 Opportunity 책임이 비교적 명확함 |
| Migration Safety | 매우 양호 | 기존 엔진을 재작성하지 않고 Adapter로 재사용함 |
| Maintainability | 양호 | 작은 객체와 테스트 가능한 계약 중심 |
| Documentation | 양호 | Discovery Domain/Application/Workflow 문서가 존재함 |
| Technical Debt | 관리 필요 | 신규·기존 엔진 병존과 Presentation 직접 의존 |
| Business Readiness | 진행 중 | 분석 기능은 풍부하나 신규 Intelligence 공식 통합 미완료 |

## 12. 최종 결론

현재 HYB는 구조를 전면 재설계해야 하는 상태가 아니다. 가장 안전하고 가치 있는
방향은 기존 Discovery/Application 경계를 유지하면서, 이미 구현된 Opportunity
Score와 Decision을 공식 Discovery 흐름에 **중복 없이 연결하는 것**이다.

따라서 Sprint 5의 첫 구현 대상은 새로운 Dataset, Ranking Strategy 또는 별도
Business Rule Engine이 아니다. 먼저 **Opportunity Intelligence Integration
Contract**를 확정하고, 기존 데이터가 실제로 지원하는 범위만 점진적으로
통합한다.
