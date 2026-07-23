# HYB Opportunity AI v0.5

## 추가 기능

- 검색/분석 결과를 SQLite DB에 자동 저장
- 최근 저장 결과 조회
- 저장 DB 경로 선택
- 필요할 때 저장 비활성화

## 실행

```powershell
python main.py "gaming mouse"
python main.py --history
python main.py --history --top 10
```

기본 DB:

```text
data/hyb_opportunity.db
```

별도 DB 사용:

```powershell
python main.py "gaming mouse" --db data/test.db
```

저장하지 않고 검색:

```powershell
python main.py "gaming mouse" --no-save
```

## 확인

```powershell
python -m pytest
```
