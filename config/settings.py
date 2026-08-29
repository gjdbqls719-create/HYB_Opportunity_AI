from __future__ import annotations

import os
import re
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

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

    @property
    def ebay_notification_public_key_url(self) -> str:
        if self.ebay_env == "production":
            return "https://api.ebay.com/commerce/notification/v1/public_key"

        return (
            "https://api.sandbox.ebay.com/commerce/notification/v1/public_key"
        )


@dataclass(frozen=True, slots=True)
class EbayAccountDeletionSettings:
    endpoint_url: str
    verification_token: str


_EBAY_VERIFICATION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,80}$")


def get_ebay_account_deletion_settings() -> EbayAccountDeletionSettings:
    endpoint_url = os.getenv(
        "EBAY_ACCOUNT_DELETION_ENDPOINT_URL",
        "",
    ).strip()
    verification_token = os.getenv(
        "EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN",
        "",
    ).strip()

    if not endpoint_url:
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_ENDPOINT_URL is not configured."
        )

    parsed_endpoint = urlsplit(endpoint_url)
    if parsed_endpoint.scheme.lower() != "https" or not parsed_endpoint.netloc:
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_ENDPOINT_URL must be an absolute HTTPS URL."
        )
    if (
        parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
    ):
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_ENDPOINT_URL must not contain credentials."
        )
    if parsed_endpoint.fragment:
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_ENDPOINT_URL must not contain a fragment."
        )

    hostname = parsed_endpoint.hostname
    if hostname is None or hostname.lower() == "localhost":
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_ENDPOINT_URL must use a public host."
        )
    try:
        endpoint_address = ip_address(hostname)
    except ValueError:
        endpoint_address = None
    if endpoint_address is not None and not endpoint_address.is_global:
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_ENDPOINT_URL must use a public host."
        )

    if not _EBAY_VERIFICATION_TOKEN_PATTERN.fullmatch(verification_token):
        raise ValueError(
            "EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN must be 32 to 80 "
            "characters using only letters, numbers, underscores, or hyphens."
        )

    return EbayAccountDeletionSettings(
        endpoint_url=endpoint_url,
        verification_token=verification_token,
    )


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
