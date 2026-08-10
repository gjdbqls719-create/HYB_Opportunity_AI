from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.application.purchase_execution import (
    PurchaseExecutionExactMatchError,
    RecordPurchaseExecution,
    RecordPurchaseExecutionCommandV2,
)
from app.application.real_money_execution_intent import (
    EvaluateRealMoneyExecutionIntent,
    EvaluateRealMoneyExecutionIntentCommandV2,
)
from app.domain.capital import (
    PURCHASE_EXECUTION_POLICY_VERSION_V2,
    REAL_MONEY_EXECUTION_SAFETY_POLICY_VERSION_V2,
    PurchaseExecutionEvidenceReference,
    RealMoneyExecutionIntentBlockingReasonCode,
    RealMoneyExecutionIntentState,
)
from test_purchase_execution import MemoryPurchaseExecutionRepository
from test_real_money_execution_intent import sources
from test_sourcing_authority_contract import NOW
from app.web import app
from app.infrastructure.purchase_execution import SQLitePurchaseExecutionRepository
from app.infrastructure.real_money_execution_intent import SQLiteRealMoneyExecutionIntentRepository
from test_real_money_execution_intent_sqlite import seed as seed_sqlite_sources


def test_v2_monetary_policies_are_explicit() -> None:
    assert REAL_MONEY_EXECUTION_SAFETY_POLICY_VERSION_V2 == "2.0.0"
    assert PURCHASE_EXECUTION_POLICY_VERSION_V2 == "2.0.0"


def _intent_command(repository, **changes):
    values = {
        "command_id": "execution-v2-command-1",
        "founder_capital_approval_id": repository.approval.approval_id,
        "quote_id": repository.admission.quote_revision.quote_id,
        "quote_revision": repository.admission.quote_revision.revision,
        "current_deployable_capital_snapshot_id": repository.current_capital.snapshot_id,
        "execution_quantity": repository.intended.quantity,
        "execution_quantity_unit": repository.intended.quantity_unit,
        "proposed_supplier_order_committed_amount": Decimal("500"),
        "supplier_order_currency": repository.admission.quote_revision.unit_price.currency,
        "supplier_order_checkout_evidence_reference": "artifact://checkout/proposed-001",
        "founder_id": repository.approval.founder_id,
        "requested_at": NOW + timedelta(days=2),
        "confirmed_at": NOW + timedelta(days=2, minutes=1),
        "current_execution_confirmed": True,
    }
    values.update(changes)
    return EvaluateRealMoneyExecutionIntentCommandV2(**values)


def _intent(repository, command=None):
    return EvaluateRealMoneyExecutionIntent(
        repository,
        execution_intent_id_generator=lambda: "execution-intent-v2-1",
        evaluated_clock=lambda: NOW + timedelta(days=2, minutes=2),
        committed_clock=lambda: NOW + timedelta(days=2, minutes=3),
    ).execute(command or _intent_command(repository)).intent


def test_intent_v2_separates_authorized_capital_from_supplier_commitment():
    repository = sources()
    intent = _intent(repository)
    source = intent.source_manifest
    assert intent.state is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
    assert source.authorized_acquisition_capital_amount == repository.approval.approved_capital
    assert source.authorized_acquisition_capital_currency == repository.approval.currency
    assert source.proposed_supplier_order_committed_amount == Decimal("500")
    assert source.supplier_order_currency == repository.admission.quote_revision.unit_price.currency
    assert source.planned_execution_amount is None
    assert source.currency is None


def test_intent_v2_wrong_supplier_currency_blocks_without_fx():
    repository = sources()
    quote_currency = repository.admission.quote_revision.unit_price.currency
    wrong = "USD" if quote_currency != "USD" else "CNY"
    intent = _intent(repository, _intent_command(repository, supplier_order_currency=wrong))
    assert intent.state is RealMoneyExecutionIntentState.BLOCKED
    assert RealMoneyExecutionIntentBlockingReasonCode.SUPPLIER_ORDER_CURRENCY_MISMATCH in intent.blocking_reasons


def test_same_currency_unequal_authorized_and_supplier_amounts_remain_distinct():
    repository = sources()
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(
            repository.admission.quote_revision,
            unit_price=replace(
                repository.admission.quote_revision.unit_price,
                currency=repository.approval.currency,
            ),
        ),
    )
    supplier_amount = repository.approval.approved_capital - Decimal("1")
    intent = _intent(
        repository,
        _intent_command(
            repository,
            proposed_supplier_order_committed_amount=supplier_amount,
            supplier_order_currency=repository.approval.currency,
        ),
    )
    assert intent.state is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
    assert intent.source_manifest.authorized_acquisition_capital_amount != supplier_amount
    assert intent.source_manifest.proposed_supplier_order_committed_amount == supplier_amount


def _purchase_command(intent, **changes):
    source = intent.source_manifest
    values = {
        "command_id": "purchase-v2-command-1",
        "real_money_execution_intent_id": intent.intent_id,
        "quote_id": source.quote_id,
        "quote_revision": source.quote_revision,
        "actual_quantity": source.execution_quantity,
        "actual_quantity_unit": source.execution_quantity_unit,
        "supplier_order_committed_amount": source.proposed_supplier_order_committed_amount,
        "supplier_order_currency": source.supplier_order_currency,
        "external_order_reference": "supplier-order-v2-001",
        "founder_id": source.founder_id,
        "executed_at": intent.evaluated_at + timedelta(minutes=1),
        "evidence_references": (
            PurchaseExecutionEvidenceReference(
                "artifact://checkout/actual-001",
                intent.evaluated_at + timedelta(minutes=1),
            ),
        ),
        "requested_at": intent.evaluated_at + timedelta(minutes=2),
    }
    values.update(changes)
    return RecordPurchaseExecutionCommandV2(**values)


def _purchase_owner(repository, intent):
    return RecordPurchaseExecution(
        repository,
        record_id_generator=lambda: "purchase-v2-1",
        admitted_clock=lambda: intent.evaluated_at + timedelta(minutes=3),
        committed_clock=lambda: intent.evaluated_at + timedelta(minutes=4),
    )


def test_purchase_v2_records_supplier_money_and_preserves_authorized_capital():
    source_repository = sources()
    intent = _intent(source_repository)
    repository = MemoryPurchaseExecutionRepository(intent, source_repository.admission)
    record = _purchase_owner(repository, intent).execute(_purchase_command(intent)).record
    assert record.supplier_order_committed_amount == Decimal("500")
    assert record.supplier_order_currency == intent.source_manifest.supplier_order_currency
    assert record.source_manifest.authorized_acquisition_capital_amount == source_repository.approval.approved_capital
    assert record.actual_total_committed_amount is None


@pytest.mark.parametrize(
    "change",
    [
        {"supplier_order_committed_amount": Decimal("510")},
        {"supplier_order_currency": "USD"},
    ],
)
def test_purchase_v2_checkout_drift_fails_closed(change):
    source_repository = sources()
    intent = _intent(source_repository)
    repository = MemoryPurchaseExecutionRepository(intent, source_repository.admission)
    with pytest.raises(PurchaseExecutionExactMatchError):
        _purchase_owner(repository, intent).execute(_purchase_command(intent, **change))


def test_v2_sqlite_round_trip_restart_and_replay_are_exact(tmp_path):
    path = tmp_path / "money-v2.sqlite3"
    approval, capital = seed_sqlite_sources(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        gate = repository.get_capital_gate(approval.capital_gate_id)
        requirement = repository.get_capital_requirement(approval.capital_requirement_id)
        admission = repository.get_sourcing_admission(
            gate.source_manifest.sourcing_admission_id,
            gate.source_manifest.sourcing_admission_revision,
        )
        intent_request = EvaluateRealMoneyExecutionIntentCommandV2(
            command_id="sqlite-intent-v2-command",
            founder_capital_approval_id=approval.approval_id,
            quote_id=gate.source_manifest.quote_id,
            quote_revision=gate.source_manifest.quote_revision,
            current_deployable_capital_snapshot_id=capital.snapshot_id,
            execution_quantity=requirement.quantity,
            execution_quantity_unit=requirement.quantity_unit,
            proposed_supplier_order_committed_amount=Decimal("500"),
            supplier_order_currency=admission.quote_revision.unit_price.currency,
            supplier_order_checkout_evidence_reference="artifact://checkout/sqlite-proposed",
            founder_id=approval.founder_id,
            requested_at=NOW + timedelta(days=5),
            confirmed_at=NOW + timedelta(days=5, minutes=1),
            current_execution_confirmed=True,
        )
        intent_owner = EvaluateRealMoneyExecutionIntent(
            repository,
            execution_intent_id_generator=lambda: "sqlite-intent-v2",
            evaluated_clock=lambda: NOW + timedelta(days=5, minutes=2),
            committed_clock=lambda: NOW + timedelta(days=5, minutes=3),
        )
        intent = intent_owner.execute(intent_request).intent
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        restored = repository.get_intent(intent.intent_id)
        assert restored == intent
        replay = EvaluateRealMoneyExecutionIntent(
            repository,
            execution_intent_id_generator=lambda: (_ for _ in ()).throw(AssertionError("identity")),
            evaluated_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            committed_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        ).execute(intent_request)
        assert replay.replayed is True
    purchase_request = _purchase_command(
        intent,
        command_id="sqlite-purchase-v2-command",
        executed_at=NOW + timedelta(days=6),
        requested_at=NOW + timedelta(days=6, minutes=1),
        evidence_references=(
            PurchaseExecutionEvidenceReference(
                "artifact://checkout/sqlite-actual", NOW + timedelta(days=6)
            ),
        ),
    )
    with SQLitePurchaseExecutionRepository(path) as repository:
        purchase_owner = RecordPurchaseExecution(
            repository,
            record_id_generator=lambda: "sqlite-purchase-v2",
            admitted_clock=lambda: NOW + timedelta(days=6, minutes=2),
            committed_clock=lambda: NOW + timedelta(days=6, minutes=3),
        )
        record = purchase_owner.execute(purchase_request).record
    with SQLitePurchaseExecutionRepository(path) as repository:
        assert repository.get_record(record.record_id) == record
        replay = RecordPurchaseExecution(
            repository,
            record_id_generator=lambda: (_ for _ in ()).throw(AssertionError("identity")),
            admitted_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            committed_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        ).execute(purchase_request)
        assert replay.replayed is True


def test_openapi_exposes_separate_v2_monetary_authorities():
    schemas = TestClient(app).get("/openapi.json").json()["components"]["schemas"]
    intent_request = schemas["RealMoneyExecutionIntentRequest"]["properties"]
    intent_response = schemas["RealMoneyExecutionIntentResponse"]["properties"]
    purchase_request = schemas["PurchaseExecutionRequest"]["properties"]
    purchase_response = schemas["PurchaseExecutionResponse"]["properties"]
    assert "contract_version" in schemas["RealMoneyExecutionIntentRequest"]["required"]
    assert "contract_version" in schemas["PurchaseExecutionRequest"]["required"]
    assert "proposed_supplier_order_committed_amount" in intent_request
    assert "authorized_acquisition_capital_amount" in intent_response
    assert "supplier_order_committed_amount" in purchase_request
    assert "authorized_acquisition_capital_amount" in purchase_response
    assert "proposed_supplier_order_committed_amount" in purchase_response
    assert "supplier_order_committed_amount" in purchase_response
