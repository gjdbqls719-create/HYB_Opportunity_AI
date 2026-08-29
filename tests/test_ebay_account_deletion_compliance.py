from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.web as web
import services.ebay_notification_verification as verification_module
from app.application.ebay_account_deletion import (
    EbayAccountDeletionAuthenticityStatus,
    EbayAccountDeletionNotification,
    EbayAccountDeletionProcessingStatus,
    EbayAccountDeletionReceipt,
    EbayAccountDeletionReceiptConflictError,
    EbayAccountDeletionReceiptPersistenceError,
    EbayAccountDeletionSignatureError,
    ReceiveEbayAccountDeletion,
    generate_ebay_account_deletion_challenge_response,
)
from app.infrastructure.ebay_account_deletion import (
    SQLiteEbayAccountDeletionReceiptRepository,
)
from config.settings import (
    EbayAccountDeletionSettings,
    Settings,
    get_ebay_account_deletion_settings,
)
from services.ebay_notification_verification import (
    EbayNotificationSignatureVerifier,
    EbayNotificationVerificationUnavailableError,
)


ENDPOINT_URL = (
    "https://example.com/api/v1/integrations/ebay/account-deletion"
)
VERIFICATION_TOKEN = "0123456789abcdef0123456789abcdef"
SIGNATURE_HEADER = "test-signature"
SUBJECT_USER_ID = "immutable-ebay-user-id"
SUBJECT_EIAS_TOKEN = "legacy-eias-token"


def make_payload(
    *,
    notification_id: str = "notification-001",
    topic: str = "MARKETPLACE_ACCOUNT_DELETION",
    schema_version: str = "1.0",
    deprecated: bool = False,
    event_date: str = "2026-08-28T01:02:03.123Z",
    publish_date: str = "2026-08-28T01:02:04.456Z",
    publish_attempt_count: int = 1,
    username: str | None = "public-ebay-name",
    user_id: str | None = SUBJECT_USER_ID,
    eias_token: str | None = SUBJECT_EIAS_TOKEN,
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if username is not None:
        data["username"] = username
    if user_id is not None:
        data["userId"] = user_id
    if eias_token is not None:
        data["eiasToken"] = eias_token
    return {
        "metadata": {
            "topic": topic,
            "schemaVersion": schema_version,
            "deprecated": deprecated,
        },
        "notification": {
            "notificationId": notification_id,
            "eventDate": event_date,
            "publishDate": publish_date,
            "publishAttemptCount": publish_attempt_count,
            "data": data,
        },
    }


def make_notification(**overrides: Any) -> EbayAccountDeletionNotification:
    payload = make_payload(**overrides)
    metadata = payload["metadata"]
    notification = payload["notification"]
    data = notification["data"]
    return EbayAccountDeletionNotification.create(
        notification_id=notification["notificationId"],
        topic=metadata["topic"],
        schema_version=metadata["schemaVersion"],
        deprecated=metadata["deprecated"],
        event_date=notification["eventDate"],
        publish_date=notification["publishDate"],
        publish_attempt_count=notification["publishAttemptCount"],
        username=data.get("username"),
        user_id=data.get("userId"),
        eias_token=data.get("eiasToken"),
    )


def make_receipt(**overrides: Any) -> EbayAccountDeletionReceipt:
    notification = make_notification(**overrides)
    return EbayAccountDeletionReceipt(
        notification=notification,
        semantic_fingerprint=notification.semantic_fingerprint,
        authenticity_status=EbayAccountDeletionAuthenticityStatus.VERIFIED,
        processing_status=(
            EbayAccountDeletionProcessingStatus.PENDING_DELETION_REVIEW
        ),
        received_at="2026-08-28T01:02:05Z",
    )


class AcceptingSignatureVerifier:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def verify(
        self,
        *,
        message: dict[str, Any],
        signature_header: str,
    ) -> bool:
        self.messages.append(message)
        return signature_header == SIGNATURE_HEADER


@pytest.fixture
def compliance_client(tmp_path: Path):
    repository = SQLiteEbayAccountDeletionReceiptRepository(
        tmp_path / "compliance.db"
    )
    verifier = AcceptingSignatureVerifier()
    ingress = ReceiveEbayAccountDeletion(
        signature_verifier=verifier,
        receipt_repository=repository,
        clock=lambda: datetime(
            2026,
            8,
            28,
            1,
            2,
            5,
            tzinfo=timezone.utc,
        ),
    )
    web.app.dependency_overrides[
        web.get_ebay_account_deletion_configuration
    ] = lambda: EbayAccountDeletionSettings(
        endpoint_url=ENDPOINT_URL,
        verification_token=VERIFICATION_TOKEN,
    )
    web.app.dependency_overrides[
        web.get_ebay_account_deletion_ingress
    ] = lambda: ingress
    try:
        with TestClient(web.app) as client:
            yield client, repository, verifier
    finally:
        web.app.dependency_overrides.pop(
            web.get_ebay_account_deletion_configuration,
            None,
        )
        web.app.dependency_overrides.pop(
            web.get_ebay_account_deletion_ingress,
            None,
        )


def test_challenge_known_vector_uses_exact_configured_values() -> None:
    assert generate_ebay_account_deletion_challenge_response(
        challenge_code="challenge-123",
        verification_token=VERIFICATION_TOKEN,
        endpoint_url=ENDPOINT_URL,
    ) == (
        "5d6d33bd8c373f7722a7836d939aa25b1353cf3ae75be1aeec336acedc6b3b98"
    )


def test_get_challenge_returns_exact_ebay_contract_and_ignores_host(
    compliance_client,
) -> None:
    client, _, _ = compliance_client

    response = client.get(
        web.EBAY_ACCOUNT_DELETION_PATH,
        params={"challenge_code": "challenge-123"},
        headers={"host": "attacker.invalid"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "challengeResponse": (
            "5d6d33bd8c373f7722a7836d939aa25b1353cf3ae75be1aeec336acedc6b3b98"
        )
    }
    assert VERIFICATION_TOKEN not in response.text


@pytest.mark.parametrize("query", [{}, {"challenge_code": ""}])
def test_get_challenge_rejects_missing_or_empty_code(
    compliance_client,
    query: dict[str, str],
) -> None:
    client, _, _ = compliance_client

    response = client.get(web.EBAY_ACCOUNT_DELETION_PATH, params=query)

    assert response.status_code == 422
    assert VERIFICATION_TOKEN not in response.text


@pytest.mark.parametrize(
    "missing_name",
    [
        "EBAY_ACCOUNT_DELETION_ENDPOINT_URL",
        "EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN",
    ],
)
def test_get_challenge_fails_closed_when_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
) -> None:
    monkeypatch.setenv("EBAY_ACCOUNT_DELETION_ENDPOINT_URL", ENDPOINT_URL)
    monkeypatch.setenv(
        "EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN",
        VERIFICATION_TOKEN,
    )
    monkeypatch.delenv(missing_name, raising=False)

    with TestClient(web.app) as client:
        response = client.get(
            web.EBAY_ACCOUNT_DELETION_PATH,
            params={"challenge_code": "challenge-123"},
        )

    assert response.status_code == 503
    assert VERIFICATION_TOKEN not in response.text
    assert ENDPOINT_URL not in response.text


def test_account_deletion_configuration_validates_official_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EBAY_ACCOUNT_DELETION_ENDPOINT_URL", ENDPOINT_URL)
    monkeypatch.setenv(
        "EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN",
        VERIFICATION_TOKEN,
    )

    settings = get_ebay_account_deletion_settings()

    assert settings.endpoint_url == ENDPOINT_URL
    assert settings.verification_token == VERIFICATION_TOKEN


@pytest.mark.parametrize(
    ("endpoint", "token"),
    [
        ("http://example.com/callback", VERIFICATION_TOKEN),
        ("https://localhost/callback", VERIFICATION_TOKEN),
        (ENDPOINT_URL, "too-short"),
        (ENDPOINT_URL, "x" * 31 + "!"),
    ],
)
def test_account_deletion_configuration_rejects_unsafe_values(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    token: str,
) -> None:
    monkeypatch.setenv("EBAY_ACCOUNT_DELETION_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN", token)

    with pytest.raises(ValueError):
        get_ebay_account_deletion_settings()


def test_sqlite_receipt_is_durable_idempotent_and_restart_safe(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "receipts.db"
    first_repository = SQLiteEbayAccountDeletionReceiptRepository(database_path)
    first = first_repository.record(make_receipt())

    retried_receipt = make_receipt(
        publish_date="2026-08-28T01:03:04.456Z",
        publish_attempt_count=2,
    )
    replay = first_repository.record(retried_receipt)
    restarted_repository = SQLiteEbayAccountDeletionReceiptRepository(
        database_path
    )
    restored = restarted_repository.get("notification-001")

    assert first.replayed is False
    assert replay.replayed is True
    assert first_repository.count() == 1
    assert restarted_repository.count() == 1
    assert restored == first.receipt
    assert replay.receipt == first.receipt
    assert restored is not None
    assert restored.notification.publish_attempt_count == 1
    assert restored.processing_status == (
        EbayAccountDeletionProcessingStatus.PENDING_DELETION_REVIEW
    )


def test_sqlite_receipt_rejects_conflicting_duplicate(tmp_path: Path) -> None:
    repository = SQLiteEbayAccountDeletionReceiptRepository(
        tmp_path / "receipts.db"
    )
    repository.record(make_receipt())

    with pytest.raises(EbayAccountDeletionReceiptConflictError):
        repository.record(make_receipt(user_id="different-user"))

    assert repository.count() == 1


def test_sqlite_receipt_stores_only_normalized_fields_and_is_append_only(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "receipts.db"
    repository = SQLiteEbayAccountDeletionReceiptRepository(database_path)
    repository.record(make_receipt())

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(ebay_account_deletion_receipts)"
            ).fetchall()
        }
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE ebay_account_deletion_receipts "
                "SET processing_status = processing_status"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM ebay_account_deletion_receipts")

    assert columns == {
        "notification_id",
        "topic",
        "schema_version",
        "deprecated",
        "event_date",
        "first_publish_date",
        "first_publish_attempt_count",
        "username",
        "user_id",
        "eias_token",
        "semantic_fingerprint",
        "authenticity_status",
        "processing_status",
        "received_at",
    }
    assert "raw_payload" not in columns
    assert "signature" not in columns
    assert "verification_token" not in columns


def test_sqlite_initialization_failure_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(EbayAccountDeletionReceiptPersistenceError):
        SQLiteEbayAccountDeletionReceiptRepository(tmp_path)


def test_sqlite_receipt_rejects_invalid_receipt_invariants(
    tmp_path: Path,
) -> None:
    repository = SQLiteEbayAccountDeletionReceiptRepository(
        tmp_path / "receipts.db"
    )
    notification = make_notification()
    invalid_receipt = EbayAccountDeletionReceipt(
        notification=notification,
        semantic_fingerprint="not-the-notification-fingerprint",
        authenticity_status=EbayAccountDeletionAuthenticityStatus.VERIFIED,
        processing_status=(
            EbayAccountDeletionProcessingStatus.PENDING_DELETION_REVIEW
        ),
        received_at="not-a-timestamp",
    )

    with pytest.raises(EbayAccountDeletionReceiptPersistenceError):
        repository.record(invalid_receipt)

    assert repository.count() == 0


def test_post_valid_notification_records_pending_verified_receipt(
    compliance_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, repository, verifier = compliance_client
    payload = make_payload()

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=payload,
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 202
    assert response.json() == {
        "acknowledgement": "ACCEPTED",
        "receiptStatus": "RECORDED",
        "authenticityStatus": "VERIFIED",
        "processingStatus": "PENDING_DELETION_REVIEW",
        "deletionExecuted": False,
    }
    assert repository.count() == 1
    assert verifier.messages == [payload]
    assert SUBJECT_USER_ID not in caplog.text
    assert SUBJECT_EIAS_TOKEN not in caplog.text
    assert SUBJECT_USER_ID not in response.text
    assert SUBJECT_EIAS_TOKEN not in response.text


def test_post_semantic_retry_is_acknowledged_without_second_row(
    compliance_client,
) -> None:
    client, repository, _ = compliance_client
    first = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(),
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )
    retry = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(
            publish_date="2026-08-28T01:03:04.456Z",
            publish_attempt_count=2,
        ),
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert first.status_code == retry.status_code == 202
    assert retry.json()["receiptStatus"] == "REPLAYED"
    assert repository.count() == 1


def test_post_conflicting_duplicate_fails_closed(compliance_client) -> None:
    client, repository, _ = compliance_client
    client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(),
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(user_id="different-user"),
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "conflicting eBay notification receipt"
    }
    assert repository.count() == 1
    assert "different-user" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        make_payload(topic="UNSUPPORTED_TOPIC"),
        make_payload(schema_version="2.0"),
        make_payload(deprecated=True),
        make_payload(username=None, user_id=None, eias_token=None),
    ],
)
def test_post_rejects_unsupported_or_incomplete_envelope(
    compliance_client,
    payload: dict[str, Any],
) -> None:
    client, repository, _ = compliance_client

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=payload,
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 422
    assert repository.count() == 0


def test_post_rejects_missing_notification_identity(compliance_client) -> None:
    client, repository, _ = compliance_client
    payload = make_payload()
    del payload["notification"]["notificationId"]

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=payload,
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 422
    assert repository.count() == 0


def test_post_rejects_malformed_json(compliance_client) -> None:
    client, repository, _ = compliance_client

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        content=b"{not-json",
        headers={
            "Content-Type": "application/json",
            "X-EBAY-SIGNATURE": SIGNATURE_HEADER,
        },
    )

    assert response.status_code == 422
    assert repository.count() == 0


@pytest.mark.parametrize("signature", [None, "wrong-signature"])
def test_post_requires_verified_signature(
    compliance_client,
    signature: str | None,
) -> None:
    client, repository, _ = compliance_client
    headers = {}
    if signature is not None:
        headers["X-EBAY-SIGNATURE"] = signature

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(),
        headers=headers,
    )

    assert response.status_code == 412
    assert repository.count() == 0


def test_post_maps_persistence_failure_to_retryable_status(
    compliance_client,
) -> None:
    client, _, _ = compliance_client

    class FailingRepository:
        def record(self, receipt):
            raise EbayAccountDeletionReceiptPersistenceError("database path")

    web.app.dependency_overrides[
        web.get_ebay_account_deletion_ingress
    ] = lambda: ReceiveEbayAccountDeletion(
        signature_verifier=AcceptingSignatureVerifier(),
        receipt_repository=FailingRepository(),
    )

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(),
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 503
    assert "database" not in response.text
    assert SUBJECT_USER_ID not in response.text


def test_post_maps_verification_dependency_failure_to_retryable_status(
    compliance_client,
) -> None:
    client, repository, _ = compliance_client

    class UnavailableVerifier:
        def verify(self, **kwargs):
            raise EbayNotificationVerificationUnavailableError(
                "oauth or public key detail"
            )

    web.app.dependency_overrides[
        web.get_ebay_account_deletion_ingress
    ] = lambda: ReceiveEbayAccountDeletion(
        signature_verifier=UnavailableVerifier(),
        receipt_repository=repository,
    )

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=make_payload(),
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "eBay notification verification is unavailable"
    }
    assert repository.count() == 0
    assert "oauth" not in response.text
    assert SUBJECT_USER_ID not in response.text


def test_post_redacts_sensitive_identifier_from_validation_errors(
    compliance_client,
) -> None:
    client, repository, _ = compliance_client
    sensitive_identifier = "sensitive-eias-" + ("x" * 2048)
    payload = make_payload(eias_token=sensitive_identifier)

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        json=payload,
        headers={"X-EBAY-SIGNATURE": SIGNATURE_HEADER},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "invalid eBay account deletion request"
    }
    assert repository.count() == 0
    assert sensitive_identifier not in response.text


def test_post_enforces_bounded_body_size(compliance_client) -> None:
    client, repository, _ = compliance_client
    oversized = json.dumps(
        {"padding": "x" * web.EBAY_ACCOUNT_DELETION_MAX_BODY_BYTES}
    )

    response = client.post(
        web.EBAY_ACCOUNT_DELETION_PATH,
        content=oversized,
        headers={
            "Content-Type": "application/json",
            "X-EBAY-SIGNATURE": SIGNATURE_HEADER,
        },
    )

    assert response.status_code == 413
    assert repository.count() == 0


def test_openapi_exposes_both_compliance_methods_and_safe_response(
    compliance_client,
) -> None:
    client, _, _ = compliance_client

    schema = client.get("/openapi.json").json()
    operations = schema["paths"][web.EBAY_ACCOUNT_DELETION_PATH]

    assert set(operations) == {"get", "post"}
    challenge_parameters = operations["get"]["parameters"]
    assert any(
        parameter["name"] == "challenge_code"
        and parameter["in"] == "query"
        and parameter["required"] is True
        for parameter in challenge_parameters
    )
    assert operations["post"]["responses"]["202"]
    header_parameters = operations["post"]["parameters"]
    assert any(
        parameter["name"] == "X-EBAY-SIGNATURE"
        and parameter["in"] == "header"
        and parameter["required"] is True
        for parameter in header_parameters
    )
    assert VERIFICATION_TOKEN not in json.dumps(schema)


OFFICIAL_EBAY_SIGNATURE = (
    "eyJhbGciOiJlY2RzYSIsImtpZCI6Ijk5MzYyNjFhLTdkN2ItNDYyMS1hMGYxLTk2"
    "Y2NiNDI4YWY0OSIsInNpZ25hdHVyZSI6Ik1FWUNJUUNmeGZJV3V4bVdjSUJRSjljNS"
    "9YN2lHREpxczJSQ0dzQkVhQWppbnlycmZBSWhBSVY2d0djVGlCdVY1S0pVaWYyaG9r"
    "eXJMK1E5c3NIa2FkK214Mm5FRTI1dyIsImRpZ2VzdCI6IlNIQTEifQ=="
)
OFFICIAL_EBAY_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----"
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEZhhxXKtR+TOvtDbgTPCkSof02qgB"
    "B7IsYOyf76ilExJ/upAa/vKIKheOoCyOpcLmi4t0b4uepb7LLjmMr90FUg=="
    "-----END PUBLIC KEY-----"
)
OFFICIAL_EBAY_MESSAGE = {
    "metadata": {
        "topic": "MARKETPLACE_ACCOUNT_DELETION",
        "schemaVersion": "1.0",
        "deprecated": False,
    },
    "notification": {
        "notificationId": (
            "49feeaeb-4982-42d9-a377-9645b8479411_"
            "33f7e043-fed8-442b-9d44-791923bd9a6d"
        ),
        "eventDate": "2021-03-19T20:43:59.462Z",
        "publishDate": "2021-03-19T20:43:59.679Z",
        "publishAttemptCount": 1,
        "data": {
            "username": "test_user",
            "userId": "ma8vp1jySJC",
            "eiasToken": (
                "nY+sHZ2PrBmdj6wVnY+sEZ2PrA2dj6wJnY+gAZGEpwmdj6x9nY+seQ=="
            ),
        },
    },
}


class PublicKeyResponse:
    ok = True

    def json(self) -> dict[str, str]:
        return {
            "key": OFFICIAL_EBAY_PUBLIC_KEY,
            "algorithm": "ECDSA",
            "digest": "SHA1",
        }


def test_signature_verifier_accepts_official_ebay_vector_and_caches_key() -> None:
    verification_module._PUBLIC_KEY_CACHE.clear()
    calls: list[tuple[str, dict[str, Any]]] = []

    def token_provider(settings: Settings) -> dict[str, str]:
        return {"access_token": "application-token"}

    def http_get(url: str, **kwargs: Any) -> PublicKeyResponse:
        calls.append((url, kwargs))
        return PublicKeyResponse()

    verifier = EbayNotificationSignatureVerifier(
        settings=Settings(
            ebay_env="production",
            ebay_client_id="client-id",
            ebay_client_secret="client-secret",
        ),
        token_provider=token_provider,
        http_get=http_get,
        monotonic_clock=lambda: 100.0,
    )

    assert verifier.verify(
        message=OFFICIAL_EBAY_MESSAGE,
        signature_header=OFFICIAL_EBAY_SIGNATURE,
    ) is True
    assert verifier.verify(
        message=OFFICIAL_EBAY_MESSAGE,
        signature_header=OFFICIAL_EBAY_SIGNATURE,
    ) is True
    assert len(calls) == 1
    assert calls[0][0] == (
        "https://api.ebay.com/commerce/notification/v1/public_key/"
        "9936261a-7d7b-4621-a0f1-96ccb428af49"
    )
    assert calls[0][1]["timeout"] == 10
    assert calls[0][1]["headers"]["Authorization"] == (
        "Bearer application-token"
    )


def test_signature_verifier_rejects_tampering_and_malformed_header() -> None:
    verification_module._PUBLIC_KEY_CACHE.clear()
    verifier = EbayNotificationSignatureVerifier(
        settings=Settings(
            ebay_env="production",
            ebay_client_id="client-id",
            ebay_client_secret="client-secret",
        ),
        token_provider=lambda settings: {"access_token": "token"},
        http_get=lambda *args, **kwargs: PublicKeyResponse(),
    )
    tampered = json.loads(json.dumps(OFFICIAL_EBAY_MESSAGE))
    tampered["notification"]["data"]["userId"] = "tampered"

    assert verifier.verify(
        message=tampered,
        signature_header=OFFICIAL_EBAY_SIGNATURE,
    ) is False
    assert verifier.verify(
        message=OFFICIAL_EBAY_MESSAGE,
        signature_header="not-base64",
    ) is False


def test_signature_verification_dependency_failure_is_not_an_acceptance() -> None:
    verification_module._PUBLIC_KEY_CACHE.clear()

    class FailedResponse:
        ok = False

        def json(self):
            return {}

    verifier = EbayNotificationSignatureVerifier(
        settings=Settings(
            ebay_env="production",
            ebay_client_id="client-id",
            ebay_client_secret="client-secret",
        ),
        token_provider=lambda settings: {"access_token": "token"},
        http_get=lambda *args, **kwargs: FailedResponse(),
    )

    with pytest.raises(EbayNotificationVerificationUnavailableError):
        verifier.verify(
            message=OFFICIAL_EBAY_MESSAGE,
            signature_header=OFFICIAL_EBAY_SIGNATURE,
        )


def test_signature_token_provider_failure_is_bounded() -> None:
    verification_module._PUBLIC_KEY_CACHE.clear()

    def failed_token_provider(settings: Settings):
        raise RuntimeError("oauth response containing credentials")

    verifier = EbayNotificationSignatureVerifier(
        settings=Settings(
            ebay_env="production",
            ebay_client_id="client-id",
            ebay_client_secret="client-secret",
        ),
        token_provider=failed_token_provider,
        http_get=lambda *args, **kwargs: PublicKeyResponse(),
    )

    with pytest.raises(
        EbayNotificationVerificationUnavailableError,
        match="verification is unavailable",
    ):
        verifier.verify(
            message=OFFICIAL_EBAY_MESSAGE,
            signature_header=OFFICIAL_EBAY_SIGNATURE,
        )


def test_receive_use_case_never_records_an_unverified_notification() -> None:
    class RejectingVerifier:
        def verify(self, **kwargs):
            return False

    class MustNotRecord:
        def record(self, receipt):
            raise AssertionError("unverified notification must not be recorded")

    ingress = ReceiveEbayAccountDeletion(
        signature_verifier=RejectingVerifier(),
        receipt_repository=MustNotRecord(),
    )

    with pytest.raises(EbayAccountDeletionSignatureError):
        ingress.execute(
            message=make_payload(),
            notification=make_notification(),
            signature_header=SIGNATURE_HEADER,
        )
