# File Structure

> 아래 구조는 이전에 확인된 프로젝트 구성과 대화에서 언급된 모듈을 기반으로 한 개념 구조다.
> 최신 ZIP Audit 후 실제 트리로 교체해야 한다.

```text
HYB_Opportunity_AI/
├─ app/
│  ├─ routes/
│  ├─ templates/
│  ├─ static/
│  └─ main.py
│
├─ collectors/
│  ├─ ebay/
│  └─ amazon/
│
├─ config/
│  ├─ settings.py
│  └─ constants.py
│
├─ database/
│  ├─ models.py
│  ├─ repository.py
│  └─ connection.py
│
├─ engine/
│  ├─ opportunity.py
│  ├─ product_matching.py
│  └─ scoring.py
│
├─ marketplaces/
│  ├─ ebay/
│  │  ├─ auth.py
│  │  ├─ client.py
│  │  └─ mapper.py
│  └─ amazon/
│
├─ models/
│  ├─ product.py
│  └─ opportunity.py
│
├─ orchestrator/
│  ├─ pipeline.py
│  └─ grouping.py
│
├─ services/
│  ├─ ebay_auth.py
│  └─ opportunity_service.py
│
├─ tests/
│  ├─ test_opportunity.py
│  ├─ test_matching.py
│  └─ test_ebay_mapper.py
│
├─ docs/
│  ├─ architecture/
│  ├─ decisions/
│  ├─ development-log/
│  └─ roadmap/
│
├─ data/
│  └─ hyb_opportunity.db
│
├─ HYB_STARTER_PACK/
├─ .env.example
├─ .gitignore
├─ requirements.txt
├─ README.md
└─ run.py
```

## 구조 원칙
- `marketplaces`: 외부 API 연결과 마켓별 응답 처리
- `models`: 내부 공통 데이터 형태
- `engine`: 독립적인 계산과 평가 로직
- `services`: 여러 기능을 묶어 사용 사례를 수행
- `orchestrator`: 전체 파이프라인 순서 관리
- `database`: 저장과 조회
- `app`: 사용자 화면과 요청 처리
- `tests`: 기능별 자동 테스트
- `docs`: 결정과 진행 기록

## Audit 시 확인할 사항
- 같은 역할의 폴더가 중복되어 있는가
- `collectors`, `marketplaces`, `services`의 책임이 겹치는가
- 실행 파일이 여러 개라 사용자가 혼동하는가
- 오래된 `v1`, `fixed`, `copy`, `backup` 파일이 남아 있는가
- 테스트 폴더가 중첩되어 있는가
