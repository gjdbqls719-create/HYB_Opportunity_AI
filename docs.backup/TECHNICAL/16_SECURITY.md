# HYB Opportunity AI
## SECURITY POLICY

Version: 1.0

## 기본 원칙
- Secret은 코드에 저장하지 않는다.
- .env는 GitHub에 커밋하지 않는다.
- 최소 권한 원칙을 따른다.

## 환경 변수
- API Key
- Database URL
- JWT Secret
- OAuth Secret

## 입력 검증
- 모든 Request Validation 수행
- SQL Injection 방지
- Command Injection 방지
- Path Traversal 방지

## 인증
- Bearer Token
- HTTPS 필수
- Token 만료 관리

## 로그
기록 금지:
- Password
- Access Token
- API Secret
- Cookie

## 의존성
- 정기적인 보안 업데이트
- 취약점 스캔 수행

## Incident 대응
1. Secret 폐기
2. 새 Secret 발급
3. 로그 분석
4. 영향 범위 확인
5. CHANGELOG 기록
