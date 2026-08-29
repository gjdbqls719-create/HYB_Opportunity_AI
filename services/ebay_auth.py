from __future__ import annotations

from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from config.settings import Settings, get_settings


EBAY_SCOPE = "https://api.ebay.com/oauth/api_scope"


def get_application_token(
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved_settings = settings or get_settings()

    response = requests.post(
        resolved_settings.ebay_token_url,
        auth=HTTPBasicAuth(
            resolved_settings.ebay_client_id,
            resolved_settings.ebay_client_secret,
        ),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": EBAY_SCOPE,
        },
        timeout=20,
    )

    if not response.ok:
        raise RuntimeError(
            "eBay 토큰 발급 실패\n"
            f"HTTP 상태: {response.status_code}\n"
            f"응답: {response.text}"
        )

    token_data = response.json()

    if "access_token" not in token_data:
        raise RuntimeError(
            "eBay 응답에 access_token이 없습니다."
        )

    return token_data
