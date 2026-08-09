from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.purchase_execution import (
    PurchaseExecutionCardinalityConflictError,
    PurchaseExecutionExactMatchError,
    PurchaseExecutionIntentStateError,
    PurchaseExecutionPublication,
    PurchaseExecutionReplayConflictError,
    RecordPurchaseExecution,
    RecordPurchaseExecutionCommand,
)
from app.domain.capital import (
    PurchaseExecutionEvidenceReference,
    RealMoneyExecutionIntentState,
)
from app.infrastructure.purchase_execution import (
    ProductionPurchaseExecutionRecordIdentityGenerator,
)
from test_real_money_execution_intent import command as intent_command
from test_real_money_execution_intent import evaluate as evaluate_intent
from test_real_money_execution_intent import sources
from test_sourcing_authority_contract import NOW


class MemoryPurchaseExecutionRepository:
    def __init__(self, intent, admission):
        self.intent = intent
        self.admission = admission
        self.results = {}
        self.record = None
        self.action_fingerprint = None

    def get_execution_intent(self, intent_id):
        return self.intent if self.intent.intent_id == intent_id else None

    def get_sourcing_admission(self, admission_id, revision):
        if self.admission.admission_id == admission_id and self.admission.revision == revision:
            return self.admission
        return None

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result is not None and result.receipt.command_fingerprint != fingerprint:
            raise PurchaseExecutionReplayConflictError("payload conflict")
        return result

    def find_alias(self, intent_id, action_fingerprint):
        if (
            self.record is not None
            and self.record.source_manifest.real_money_execution_intent_id == intent_id
            and self.action_fingerprint == action_fingerprint
        ):
            return self.record
        return None

    def save_alias(self, command, record, receipt):
        result = PurchaseExecutionPublication(record, receipt, True)
        self.results[command.command_id] = result
        return result

    def save_record(self, command, record, receipt):
        if self.record is not None:
            if self.action_fingerprint != command.action_fingerprint:
                raise PurchaseExecutionCardinalityConflictError("already executed")
            return self.save_alias(command, self.record, receipt)
        result = PurchaseExecutionPublication(record, receipt, False)
        self.record = record
        self.action_fingerprint = command.action_fingerprint
        self.results[command.command_id] = result
        return result


def prepared(*, blocked=False):
    source_repository = sources()
    request = intent_command(
        source_repository,
        **({"execution_quantity": 1} if blocked else {}),
    )
    intent = evaluate_intent(source_repository, request).intent
    repository = MemoryPurchaseExecutionRepository(intent, source_repository.admission)
    return repository


def command(repository, **changes):
    source = repository.intent.source_manifest
    values = {
        "command_id": "purchase-execution-command-1",
        "real_money_execution_intent_id": repository.intent.intent_id,
        "quote_id": source.quote_id,
        "quote_revision": source.quote_revision,
        "actual_quantity": source.execution_quantity,
        "actual_quantity_unit": source.execution_quantity_unit,
        "actual_total_committed_amount": source.planned_execution_amount,
        "currency": source.currency,
        "external_order_reference": "opaque-supplier-order-001",
        "founder_id": source.founder_id,
        "executed_at": repository.intent.evaluated_at + timedelta(minutes=1),
        "evidence_references": (
            PurchaseExecutionEvidenceReference(
                "artifact://order-confirmation/001",
                repository.intent.evaluated_at + timedelta(minutes=1),
            ),
        ),
        "requested_at": repository.intent.evaluated_at + timedelta(minutes=2),
    }
    values.update(changes)
    return RecordPurchaseExecutionCommand(**values)


def owner(repository, identity="purchase-record-1"):
    return RecordPurchaseExecution(
        repository,
        record_id_generator=lambda: identity,
        admitted_clock=lambda: repository.intent.evaluated_at + timedelta(minutes=3),
        committed_clock=lambda: repository.intent.evaluated_at + timedelta(minutes=4),
    )


def test_ready_intent_admits_immutable_exact_purchase_with_reconstructed_lineage():
    repository = prepared()
    publication = owner(repository).execute(command(repository))
    record = publication.record
    source = record.source_manifest
    assert publication.replayed is False
    assert record.record_id == "purchase-record-1"
    assert source.opportunity_identity == repository.intent.source_manifest.opportunity_identity
    assert source.real_money_execution_intent_id == repository.intent.intent_id
    assert source.supplier_id == repository.admission.supplier_identity.supplier_id
    assert source.external_product_reference == repository.admission.sourcing_product_identity.external_product_reference
    assert record.external_order_reference == "opaque-supplier-order-001"
    assert record.evidence_references[0].reference == "artifact://order-confirmation/001"
    assert not hasattr(record, "state")
    assert not hasattr(record, "inventory")
    assert not hasattr(record, "actual_economics")
    with pytest.raises(FrozenInstanceError):
        record.external_order_reference = "changed"


def test_blocked_intent_cannot_be_recorded():
    repository = prepared(blocked=True)
    assert repository.intent.state is RealMoneyExecutionIntentState.BLOCKED
    with pytest.raises(PurchaseExecutionIntentStateError):
        owner(repository).execute(command(repository))


@pytest.mark.parametrize(
    "change",
    (
        {"quote_id": "different-quote"},
        {"quote_revision": 999},
        {"actual_quantity": 999},
        {"actual_quantity_unit": "case"},
        {"actual_total_committed_amount": Decimal("1")},
        {"currency": "USD"},
        {"founder_id": "different-founder"},
    ),
)
def test_exact_match_policy_rejects_deviated_actual_purchase(change):
    repository = prepared()
    with pytest.raises(PurchaseExecutionExactMatchError):
        owner(repository).execute(command(repository, **change))
    assert repository.record is None


def test_same_command_replays_and_changed_payload_conflicts_without_new_clocks():
    repository = prepared()
    request = command(repository)
    first = owner(repository).execute(request)
    replay = RecordPurchaseExecution(
        repository,
        record_id_generator=lambda: (_ for _ in ()).throw(AssertionError("identity")),
        admitted_clock=lambda: (_ for _ in ()).throw(AssertionError("admitted clock")),
        committed_clock=lambda: (_ for _ in ()).throw(AssertionError("committed clock")),
    ).execute(request)
    assert replay.replayed is True
    assert replay.record is first.record
    assert replay.receipt is first.receipt
    with pytest.raises(PurchaseExecutionReplayConflictError):
        owner(repository).execute(
            command(repository, external_order_reference="different")
        )


def test_different_command_identical_actual_event_aliases_one_record():
    repository = prepared()
    first = owner(repository).execute(command(repository))
    second = owner(repository, identity="must-not-be-used").execute(
        command(
            repository,
            command_id="purchase-execution-command-2",
            requested_at=NOW + timedelta(days=10),
        )
    )
    assert second.replayed is True
    assert second.record.record_id == first.record.record_id
    assert len(repository.results) == 2


def test_one_ready_intent_cannot_have_competing_actual_execution():
    repository = prepared()
    owner(repository).execute(command(repository))
    with pytest.raises(PurchaseExecutionCardinalityConflictError):
        owner(repository).execute(
            command(
                repository,
                command_id="purchase-execution-command-2",
                external_order_reference="another-external-order",
            )
        )


def test_execution_time_must_be_aware_and_not_precede_ready_intent():
    repository = prepared()
    with pytest.raises(ValueError, match="timezone-aware"):
        command(repository, executed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="cannot precede READY"):
        owner(repository).execute(
            command(repository, executed_at=repository.intent.evaluated_at - timedelta(seconds=1))
        )


def test_production_purchase_record_identity_is_stateless_uuid4_hex():
    identity = ProductionPurchaseExecutionRecordIdentityGenerator()
    first, second = identity(), identity()
    assert first != second
    assert len(first) == len(second) == 32
    assert all(character in "0123456789abcdef" for character in first + second)
