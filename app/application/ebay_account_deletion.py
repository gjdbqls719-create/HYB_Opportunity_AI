from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


EBAY_ACCOUNT_DELETION_TOPIC = "MARKETPLACE_ACCOUNT_DELETION"
EBAY_ACCOUNT_DELETION_SCHEMA_VERSION = "1.0"


class EbayAccountDeletionAuthenticityStatus(str, Enum):
    VERIFIED = "VERIFIED"


class EbayAccountDeletionProcessingStatus(str, Enum):
    PENDING_DELETION_REVIEW = "PENDING_DELETION_REVIEW"


class EbayAccountDeletionValidationError(ValueError):
    """Raised when a notification cannot form an authoritative receipt."""


class EbayAccountDeletionSignatureError(RuntimeError):
    """Raised when notification authenticity cannot be established."""


class EbayAccountDeletionReceiptConflictError(RuntimeError):
    """Raised when one notification ID carries conflicting semantic data."""


class EbayAccountDeletionReceiptPersistenceError(RuntimeError):
    """Raised when a durable receipt cannot be committed or reconstructed."""


def generate_ebay_account_deletion_challenge_response(
    *,
    challenge_code: str,
    verification_token: str,
    endpoint_url: str,
) -> str:
    if not isinstance(challenge_code, str) or not challenge_code.strip():
        raise EbayAccountDeletionValidationError(
            "challenge_code must be non-empty text"
        )
    if len(challenge_code) > 1024:
        raise EbayAccountDeletionValidationError("challenge_code is too long")
    if not isinstance(verification_token, str) or not verification_token:
        raise EbayAccountDeletionValidationError(
            "verification token is unavailable"
        )
    if not isinstance(endpoint_url, str) or not endpoint_url:
        raise EbayAccountDeletionValidationError(
            "configured endpoint URL is unavailable"
        )

    challenge_material = (
        challenge_code + verification_token + endpoint_url
    ).encode("utf-8")
    return hashlib.sha256(challenge_material).hexdigest()


def _required_text(value: str, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EbayAccountDeletionValidationError(
            f"{field_name} must be non-empty text"
        )
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise EbayAccountDeletionValidationError(f"{field_name} is too long")
    return cleaned


def _optional_identifier(
    value: str | None,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name, maximum=2048)


def _utc_timestamp_text(value: str, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name, maximum=128)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise EbayAccountDeletionValidationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EbayAccountDeletionValidationError(
            f"{field_name} must include a timezone"
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _clock_text(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise EbayAccountDeletionReceiptPersistenceError(
            "receipt clock returned an invalid value"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise EbayAccountDeletionReceiptPersistenceError(
            "receipt clock must be timezone-aware"
        )
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class EbayAccountDeletionNotification:
    notification_id: str
    topic: str
    schema_version: str
    deprecated: bool
    event_date: str
    publish_date: str
    publish_attempt_count: int
    username: str | None
    user_id: str | None
    eias_token: str | None

    @classmethod
    def create(
        cls,
        *,
        notification_id: str,
        topic: str,
        schema_version: str,
        deprecated: bool,
        event_date: str,
        publish_date: str,
        publish_attempt_count: int,
        username: str | None,
        user_id: str | None,
        eias_token: str | None,
    ) -> EbayAccountDeletionNotification:
        cleaned_topic = _required_text(
            topic,
            field_name="metadata.topic",
            maximum=128,
        )
        if cleaned_topic != EBAY_ACCOUNT_DELETION_TOPIC:
            raise EbayAccountDeletionValidationError(
                "unsupported notification topic"
            )

        cleaned_schema_version = _required_text(
            schema_version,
            field_name="metadata.schemaVersion",
            maximum=32,
        )
        if cleaned_schema_version != EBAY_ACCOUNT_DELETION_SCHEMA_VERSION:
            raise EbayAccountDeletionValidationError(
                "unsupported notification schema version"
            )
        if type(deprecated) is not bool:
            raise EbayAccountDeletionValidationError(
                "metadata.deprecated must be a boolean"
            )
        if deprecated:
            raise EbayAccountDeletionValidationError(
                "deprecated notification schema is not supported"
            )
        if type(publish_attempt_count) is not int or publish_attempt_count < 1:
            raise EbayAccountDeletionValidationError(
                "notification.publishAttemptCount must be a positive integer"
            )

        cleaned_username = _optional_identifier(
            username,
            field_name="notification.data.username",
        )
        cleaned_user_id = _optional_identifier(
            user_id,
            field_name="notification.data.userId",
        )
        cleaned_eias_token = _optional_identifier(
            eias_token,
            field_name="notification.data.eiasToken",
        )
        if not any((cleaned_username, cleaned_user_id, cleaned_eias_token)):
            raise EbayAccountDeletionValidationError(
                "notification.data requires at least one user identifier"
            )

        return cls(
            notification_id=_required_text(
                notification_id,
                field_name="notification.notificationId",
                maximum=512,
            ),
            topic=cleaned_topic,
            schema_version=cleaned_schema_version,
            deprecated=deprecated,
            event_date=_utc_timestamp_text(
                event_date,
                field_name="notification.eventDate",
            ),
            publish_date=_utc_timestamp_text(
                publish_date,
                field_name="notification.publishDate",
            ),
            publish_attempt_count=publish_attempt_count,
            username=cleaned_username,
            user_id=cleaned_user_id,
            eias_token=cleaned_eias_token,
        )

    @property
    def semantic_fingerprint(self) -> str:
        semantic_payload = {
            "deprecated": self.deprecated,
            "eventDate": self.event_date,
            "notificationId": self.notification_id,
            "schemaVersion": self.schema_version,
            "subject": {
                "eiasToken": self.eias_token,
                "userId": self.user_id,
                "username": self.username,
            },
            "topic": self.topic,
        }
        canonical = json.dumps(
            semantic_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EbayAccountDeletionReceipt:
    notification: EbayAccountDeletionNotification
    semantic_fingerprint: str
    authenticity_status: EbayAccountDeletionAuthenticityStatus
    processing_status: EbayAccountDeletionProcessingStatus
    received_at: str


@dataclass(frozen=True, slots=True)
class EbayAccountDeletionReceiptResult:
    receipt: EbayAccountDeletionReceipt
    replayed: bool


class EbayAccountDeletionSignatureVerifier(Protocol):
    def verify(
        self,
        *,
        message: Mapping[str, Any],
        signature_header: str,
    ) -> bool: ...


class EbayAccountDeletionReceiptRepository(Protocol):
    def record(
        self,
        receipt: EbayAccountDeletionReceipt,
    ) -> EbayAccountDeletionReceiptResult: ...


class ReceiveEbayAccountDeletion:
    def __init__(
        self,
        *,
        signature_verifier: EbayAccountDeletionSignatureVerifier,
        receipt_repository: EbayAccountDeletionReceiptRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._signature_verifier = signature_verifier
        self._receipt_repository = receipt_repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(
        self,
        *,
        message: Mapping[str, Any],
        notification: EbayAccountDeletionNotification,
        signature_header: str,
    ) -> EbayAccountDeletionReceiptResult:
        if not isinstance(signature_header, str) or not signature_header.strip():
            raise EbayAccountDeletionSignatureError(
                "notification signature is required"
            )
        if not self._signature_verifier.verify(
            message=message,
            signature_header=signature_header,
        ):
            raise EbayAccountDeletionSignatureError(
                "notification signature is invalid"
            )

        receipt = EbayAccountDeletionReceipt(
            notification=notification,
            semantic_fingerprint=notification.semantic_fingerprint,
            authenticity_status=(
                EbayAccountDeletionAuthenticityStatus.VERIFIED
            ),
            processing_status=(
                EbayAccountDeletionProcessingStatus.PENDING_DELETION_REVIEW
            ),
            received_at=_clock_text(self._clock()),
        )
        return self._receipt_repository.record(receipt)


__all__ = [
    "EBAY_ACCOUNT_DELETION_SCHEMA_VERSION",
    "EBAY_ACCOUNT_DELETION_TOPIC",
    "EbayAccountDeletionAuthenticityStatus",
    "EbayAccountDeletionNotification",
    "EbayAccountDeletionProcessingStatus",
    "EbayAccountDeletionReceipt",
    "EbayAccountDeletionReceiptConflictError",
    "EbayAccountDeletionReceiptPersistenceError",
    "EbayAccountDeletionReceiptRepository",
    "EbayAccountDeletionReceiptResult",
    "EbayAccountDeletionSignatureError",
    "EbayAccountDeletionSignatureVerifier",
    "EbayAccountDeletionValidationError",
    "ReceiveEbayAccountDeletion",
    "generate_ebay_account_deletion_challenge_response",
]
