# HYB Opportunity AI
## DEVELOPMENT ENVIRONMENT

Version: 1.0

## 권장 환경
- Python 3.12+
- Git
- VS Code
- Docker Desktop

## VS Code 확장
- Python
- Pylance
- Ruff
- Docker
- GitLens

## 초기 설정

```bash
git clone <repository>
cd <repository>

python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

## 환경 변수

```text
cp .env.example .env
```

필요한 API Key를 입력한다.

## 개발 시작

```bash
ruff check .
black .
pytest
uvicorn app.main:app --reload
```

## 체크리스트
- 가상환경 활성화
- .env 설정
- 테스트 통과
- 최신 main 반영
- CHANGELOG 확인
