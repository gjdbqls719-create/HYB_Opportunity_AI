# HYB Opportunity AI
## DEPLOYMENT GUIDE

Version: 1.0

## 목표
개발(Development) → 스테이징(Staging) → 운영(Production) 환경을 동일한 절차로 배포한다.

## 환경
- Development: 로컬 개발
- Staging: 운영 전 검증
- Production: 실제 서비스

## 권장 구성
- Docker
- Docker Compose
- GitHub Actions
- PostgreSQL
- Redis
- Nginx

## 배포 절차
1. main 브랜치 최신화
2. Ruff / Black / Mypy / Pytest 통과
3. Docker 이미지 생성
4. 환경 변수 확인
5. Staging 배포
6. Smoke Test
7. Production 배포
8. Health Check
9. 모니터링 확인

## 롤백
- 이전 Docker Image 유지
- DB Migration은 롤백 가능하도록 작성
- 장애 발생 시 이전 Release Tag로 복구

## 백업
- DB: 매일
- 로그: 30일
- 업로드 파일: 주기적 백업

## 모니터링
- API 응답시간
- 오류율
- CPU / Memory
- Marketplace 연결 상태
- Scheduler 상태
