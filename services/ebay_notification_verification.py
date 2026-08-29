from __future__ import annotations

import base64
import binascii
import json
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote

import requests
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from config.settings import Settings
from services.ebay_auth import get_application_token


PUBLIC_KEY_CACHE_SECONDS = 60 * 60
MAX_SIGNATURE_HEADER_LENGTH = 8192


class EbayNotificationVerificationUnavailableError(RuntimeError):
    """Raised when eBay authenticity infrastructure cannot be reached safely."""


_PUBLIC_KEY_CACHE: dict[tuple[str, str], tuple[float, dict[str, str]]] = {}
_PUBLIC_KEY_CACHE_LOCK = threading.Lock()


class EbayNotificationSignatureVerifier:
    def __init__(
        self,
        *,
        settings: Settings,
        token_provider: Callable[[Settings], Mapping[str, Any]] = (
            get_application_token
        ),
        http_get: Callable[..., Any] = requests.get,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._http_get = http_get
        self._monotonic_clock = monotonic_clock

    def verify(
        self,
        *,
        message: Mapping[str, Any],
        signature_header: str,
    ) -> bool:
        signature_metadata = self._decode_signature_header(signature_header)
        if signature_metadata is None:
            return False

        key_id = signature_metadata.get("kid")
        algorithm = signature_metadata.get("alg")
        digest = signature_metadata.get("digest")
        encoded_signature = signature_metadata.get("signature")
        if not all(
            isinstance(value, str) and value
            for value in (key_id, algorithm, digest, encoded_signature)
        ):
            return False
        if len(key_id) > 512:
            return False
        if algorithm.lower() != "ecdsa" or digest.upper() != "SHA1":
            return False

        public_key_data = self._get_public_key(key_id)
        if public_key_data["algorithm"].upper() != "ECDSA":
            return False
        if public_key_data["digest"].upper() != "SHA1":
            return False

        try:
            signature = base64.b64decode(encoded_signature, validate=True)
            public_key = serialization.load_pem_public_key(
                self._format_public_key(public_key_data["key"]),
            )
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                return False
            serialized_message = json.dumps(
                message,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            public_key.verify(
                signature,
                serialized_message,
                ec.ECDSA(hashes.SHA1()),
            )
        except (
            InvalidSignature,
            UnsupportedAlgorithm,
            UnicodeError,
            OverflowError,
            ValueError,
            TypeError,
            binascii.Error,
        ):
            return False
        return True

    @staticmethod
    def _decode_signature_header(
        signature_header: str,
    ) -> dict[str, Any] | None:
        if (
            not isinstance(signature_header, str)
            or not signature_header
            or len(signature_header) > MAX_SIGNATURE_HEADER_LENGTH
        ):
            return None
        try:
            decoded = base64.b64decode(signature_header, validate=True)
            parsed = json.loads(decoded.decode("ascii"))
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            binascii.Error,
        ):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _format_public_key(key: str) -> bytes:
        if not isinstance(key, str):
            raise ValueError("public key must be text")
        begin = "-----BEGIN PUBLIC KEY-----"
        end = "-----END PUBLIC KEY-----"
        if begin not in key or end not in key:
            raise ValueError("public key format is unsupported")
        body = key.split(begin, 1)[1].split(end, 1)[0]
        compact_body = "".join(body.split())
        if not compact_body:
            raise ValueError("public key body is empty")
        return f"{begin}\n{compact_body}\n{end}\n".encode("ascii")

    def _get_public_key(self, key_id: str) -> dict[str, str]:
        cache_key = (self._settings.ebay_env, key_id)
        now = self._monotonic_clock()
        with _PUBLIC_KEY_CACHE_LOCK:
            cached = _PUBLIC_KEY_CACHE.get(cache_key)
            if cached is not None and cached[0] > now:
                return cached[1]

        try:
            token_data = self._token_provider(self._settings)
            access_token = token_data.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("application token is unavailable")
            public_key_url = (
                f"{self._settings.ebay_notification_public_key_url}/"
                f"{quote(key_id, safe='')}"
            )
            response = self._http_get(
                public_key_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            if not response.ok:
                raise ValueError("public key request failed")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("public key response is invalid")
            public_key_data = {
                "algorithm": self._required_public_key_text(
                    payload.get("algorithm")
                ),
                "digest": self._required_public_key_text(payload.get("digest")),
                "key": self._required_public_key_text(payload.get("key")),
            }
        except (
            requests.RequestException,
            RuntimeError,
            ValueError,
            TypeError,
        ) as error:
            raise EbayNotificationVerificationUnavailableError(
                "eBay notification verification is unavailable"
            ) from error

        with _PUBLIC_KEY_CACHE_LOCK:
            _PUBLIC_KEY_CACHE[cache_key] = (
                now + PUBLIC_KEY_CACHE_SECONDS,
                public_key_data,
            )
        return public_key_data

    @staticmethod
    def _required_public_key_text(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("public key response field is invalid")
        return value.strip()


__all__ = [
    "EbayNotificationSignatureVerifier",
    "EbayNotificationVerificationUnavailableError",
    "MAX_SIGNATURE_HEADER_LENGTH",
    "PUBLIC_KEY_CACHE_SECONDS",
]
