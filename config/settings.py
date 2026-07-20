from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    ebay_env: str
    ebay_client_id: str
    ebay_client_secret: str

    @property
    def ebay_token_url(self) -> str:
        if self.ebay_env == "production":
            return "https://api.ebay.com/identity/v1/oauth2/token"

        return "https://api.sandbox.ebay.com/identity/v1/oauth2/token"

    @property
    def ebay_browse_api_url(self) -> str:
        if self.ebay_env == "production":
            return "https://api.ebay.com/buy/browse/v1"

        return "https://api.sandbox.ebay.com/buy/browse/v1"


def get_settings() -> Settings:
    ebay_env = os.getenv("EBAY_ENV", "sandbox").strip().lower()
    ebay_client_id = os.getenv("EBAY_CLIENT_ID", "").strip()
    ebay_client_secret = os.getenv(
        "EBAY_CLIENT_SECRET",
        "",
    ).strip()

    if ebay_env not in {"sandbox", "production"}:
        raise ValueError(
            "EBAY_ENV는 sandbox 또는 production이어야 합니다."
        )

    if not ebay_client_id:
        raise ValueError(
            "EBAY_CLIENT_ID가 .env 파일에 설정되지 않았습니다."
        )

    if not ebay_client_secret:
        raise ValueError(
            "EBAY_CLIENT_SECRET이 .env 파일에 설정되지 않았습니다."
        )

    return Settings(
        ebay_env=ebay_env,
        ebay_client_id=ebay_client_id,
        ebay_client_secret=ebay_client_secret,
    )