from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import re
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.application.ocr import OCRExecutionConflictError
from app.infrastructure.external_signal_ledger import (
    ProductionOCRCandidateIdentityGenerator,
    SQLiteExternalSignalLedgerRepository,
)
from app.infrastructure.external_signal_ledger import identity_suppliers
from test_external_ocr_execution_persistence import (
    Fail,
    command,
    count,
    entry,
    result,
)


OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


def test_ocr_candidate_identity_supplier_is_public_callable_and_stateless() -> None:
    supplier = ProductionOCRCandidateIdentityGenerator()

    candidate_id = supplier()

    assert callable(supplier)
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")
    assert candidate_id
    assert OPAQUE_ID.fullmatch(candidate_id)
    assert UUID(hex=candidate_id).version == 4
    assert UUID(hex=candidate_id).hex == candidate_id


def test_ocr_candidate_identity_supplier_returns_uuid4_hex_without_transform(
    monkeypatch,
) -> None:
    expected = "0123456789abcdef0123456789abcdef"
    monkeypatch.setattr(
        identity_suppliers,
        "uuid4",
        lambda: SimpleNamespace(hex=expected),
    )

    assert ProductionOCRCandidateIdentityGenerator()() == expected


def test_shared_ocr_candidate_identity_supplier_is_concurrently_unique() -> None:
    supplier = ProductionOCRCandidateIdentityGenerator()

    with ThreadPoolExecutor(max_workers=16) as pool:
        candidate_ids = tuple(pool.map(lambda _: supplier(), range(512)))

    assert len(candidate_ids) == 512
    assert len(set(candidate_ids)) == 512
    assert all(OPAQUE_ID.fullmatch(candidate_id) for candidate_id in candidate_ids)
    assert all(UUID(hex=candidate_id).version == 4 for candidate_id in candidate_ids)


def test_fresh_execution_uses_supplier_once_per_ordered_field(monkeypatch) -> None:
    issued = iter(
        (
            SimpleNamespace(hex="1" * 32),
            SimpleNamespace(hex="2" * 32),
        )
    )
    calls = 0

    def supply_uuid():
        nonlocal calls
        calls += 1
        return next(issued)

    monkeypatch.setattr(identity_suppliers, "uuid4", supply_uuid)
    repository = SQLiteExternalSignalLedgerRepository(":memory:")

    admitted = entry(
        repository,
        identities=ProductionOCRCandidateIdentityGenerator(),
    ).execute(command())

    assert calls == 2
    assert admitted.receipt.ordered_candidate_ids == ("1" * 32, "2" * 32)
    assert tuple(value.candidate_id for value in admitted.candidates) == (
        "1" * 32,
        "2" * 32,
    )
    assert tuple(
        repository.get_candidate(candidate_id)
        for candidate_id in admitted.receipt.ordered_candidate_ids
    ) == admitted.candidates


def test_zero_field_execution_does_not_call_supplier(monkeypatch) -> None:
    def fail_uuid4():
        raise AssertionError("zero-field execution must not issue Candidate identity")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)
    repository = SQLiteExternalSignalLedgerRepository(":memory:")

    admitted = entry(
        repository,
        identities=ProductionOCRCandidateIdentityGenerator(),
    ).execute(command(result_value=result(fields=())))

    assert admitted.candidates == ()
    assert admitted.receipt.ordered_candidate_ids == ()


def test_exact_replay_does_not_call_supplier(monkeypatch) -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    first = entry(
        repository,
        identities=ProductionOCRCandidateIdentityGenerator(),
    ).execute(command())

    def fail_uuid4():
        raise AssertionError("exact replay must not issue Candidate identity")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)
    replay = entry(
        repository,
        identities=ProductionOCRCandidateIdentityGenerator(),
        artifact_clock=Fail("replay must not call artifact clock"),
        receipt_clock=Fail("replay must not call receipt clock"),
    ).execute(command())

    assert replay == replace(first, replayed=True)


def test_restart_replay_does_not_call_supplier(tmp_path, monkeypatch) -> None:
    database = tmp_path / "ocr-candidate-identity.sqlite3"
    repository = SQLiteExternalSignalLedgerRepository(database)
    first = entry(
        repository,
        identities=ProductionOCRCandidateIdentityGenerator(),
    ).execute(command())
    repository.close()

    def fail_uuid4():
        raise AssertionError("restart replay must not issue Candidate identity")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)
    restarted = SQLiteExternalSignalLedgerRepository(database)
    try:
        replay = entry(
            restarted,
            identities=ProductionOCRCandidateIdentityGenerator(),
            artifact_clock=Fail("replay must not call artifact clock"),
            receipt_clock=Fail("replay must not call receipt clock"),
        ).execute(command())

        assert replay == replace(first, replayed=True)
    finally:
        restarted.close()


def test_changed_payload_conflict_does_not_issue_replacement_identity(
    monkeypatch,
) -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    first = entry(
        repository,
        identities=ProductionOCRCandidateIdentityGenerator(),
    ).execute(command())

    def fail_uuid4():
        raise AssertionError("execution conflict must not issue Candidate identity")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)
    with pytest.raises(OCRExecutionConflictError):
        entry(
            repository,
            identities=ProductionOCRCandidateIdentityGenerator(),
            artifact_clock=Fail("conflict must not call artifact clock"),
            receipt_clock=Fail("conflict must not call receipt clock"),
        ).execute(command(result_value=result(provider_version="changed")))

    assert count(repository, "ocr_candidate_history") == 2
    assert count(repository, "ocr_execution_receipts") == 1
    assert repository.get_execution_receipt(
        first.receipt.provider,
        first.receipt.request_id,
        first.receipt.artifact_id,
    ) == first.receipt


def test_supplier_is_a_distinct_type_from_opportunity_candidate_supplier() -> None:
    from app.infrastructure.discovery import ProductionCandidateIdentityGenerator

    assert (
        ProductionOCRCandidateIdentityGenerator
        is not ProductionCandidateIdentityGenerator
    )
    assert not isinstance(
        ProductionOCRCandidateIdentityGenerator(),
        ProductionCandidateIdentityGenerator,
    )
