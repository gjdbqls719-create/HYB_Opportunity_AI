# HYB Opportunity AI
## TROUBLESHOOTING

Version: 1.0

## 목적
자주 발생하는 문제와 해결 절차를 기록한다.

## Git
- pull 충돌 → 변경사항 Commit/Stash 후 Pull
- 잘못된 Commit → git revert 우선 사용

## Python
- ModuleNotFoundError → 가상환경 활성화 및 pip install -r requirements.txt
- ImportError → Python 인터프리터 확인

## Marketplace
- 401 → API Key 확인
- 429 → Retry-After 적용
- Timeout → 재시도 및 네트워크 확인

## Database
- 연결 실패 → DATABASE_URL 확인
- Migration 실패 → Alembic 상태 확인

## Docker
- 컨테이너 종료 → docker logs 확인
- 이미지 재생성 → docker compose build --no-cache

## FastAPI
- /health 확인
- uvicorn 로그 확인

## 원칙
문제가 해결되면 원인과 해결 방법을 이 문서에 추가한다.
