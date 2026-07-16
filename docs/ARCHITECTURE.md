# Architecture

1. collectors: 상품 데이터 수집
2. engine: 수익성·기회 점수 계산
3. database: 상품과 기회 저장
4. app: 사용자 화면
5. services: 알림·스케줄·내보내기

원칙:
- 공식 API 우선
- 수집과 분석 분리
- 공통 데이터 형식 사용
- 계산식은 테스트로 검증
