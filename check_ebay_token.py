from config.settings import get_settings
from services.ebay_auth import get_application_token


settings = get_settings()
token_data = get_application_token()

access_token = token_data["access_token"]
expires_in = token_data.get("expires_in", "알 수 없음")

print("eBay 환경:", settings.ebay_env)
print("OAuth 연결 성공")
print("토큰 앞부분:", access_token[:12] + "...")
print("유효시간(초):", expires_in)