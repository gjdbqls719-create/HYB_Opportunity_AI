from dataclasses import replace
from decimal import Decimal

import pytest

from app.application.verified_economics_admission import (
    FinalizeVerifiedEconomicsAdmission,
    FinalizeVerifiedEconomicsAdmissionCommand,
    VerifiedEconomicsAdmissionConflictError,
    VerifiedEconomicsAdmissionPersistenceError,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.opportunity import OpportunityLifecycle
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from test_new_to_market_competition_demand_target_support import _target_o2
from test_sourcing_authority_contract import NOW
from test_verified_economics import complete_input


def _command(opportunity_id, *, command_id="target-economics-command-1", inputs=None):
    return FinalizeVerifiedEconomicsAdmissionCommand(
        opportunity_id=opportunity_id,
        command_id=command_id,
        operator_id="founder-1",
        inputs=complete_input() if inputs is None else inputs,
        snapshot_at=NOW,
    )


def _with_sale_price(value: str, reference: str):
    inputs = complete_input()
    sale = replace(
        inputs.expected_sale_price,
        amount=Decimal(value),
        evidence=replace(
            inputs.expected_sale_price.evidence,
            source="founder-target-price-review",
            reference=reference,
        ),
    )
    return replace(inputs, expected_sale_price=sale)


def test_existing_market_and_target_subjects_admit_same_snapshot_authority(tmp_path):
    path, publication = _target_o2(tmp_path)
    target_o2 = publication.lifecycle.opportunity_id
    repository = SQLiteValidationQueueRepository(path)
    owner = FinalizeVerifiedEconomicsAdmission(repository)
    try:
        market_result = owner.execute(
            _command("opportunity-v2-1", command_id="market-economics-command")
        )
        target_inputs = _with_sale_price("333.00", "target-price-review:0065-1")
        target_result = owner.execute(_command(target_o2, inputs=target_inputs))
    finally:
        repository.close()

    assert isinstance(market_result.snapshot, VerifiedEconomicsSnapshot)
    assert isinstance(target_result.snapshot, VerifiedEconomicsSnapshot)
    assert target_result.snapshot.opportunity_id == target_o2
    assert target_result.snapshot.inputs == target_inputs
    assert target_result.snapshot.inputs.expected_sale_price.amount == Decimal("333.00")
    assert not hasattr(target_result.snapshot, "target_identity")
    assert not hasattr(target_result.snapshot, "market_observation_identity")


def test_target_admission_never_copies_o1_economics(tmp_path):
    path, publication = _target_o2(tmp_path)
    target_o2 = publication.lifecycle.opportunity_id
    repository = SQLiteValidationQueueRepository(path)
    owner = FinalizeVerifiedEconomicsAdmission(repository)
    source_inputs = _with_sale_price("111.00", "source-o1-price")
    target_inputs = _with_sale_price("333.00", "target-o2-price")
    try:
        owner.execute(
            _command(
                "opportunity-v2-1",
                command_id="source-economics-command",
                inputs=source_inputs,
            )
        )
        owner.execute(_command(target_o2, inputs=target_inputs))
        source = repository.get_verified_economics_snapshot("opportunity-v2-1")
        target = repository.get_verified_economics_snapshot(target_o2)
    finally:
        repository.close()

    assert source.inputs == source_inputs
    assert target.inputs == target_inputs
    assert target.inputs != source.inputs


def test_no_operational_subject_fails_as_conflict():
    repository = SQLiteValidationQueueRepository(":memory:")
    lifecycle = OpportunityLifecycle("unbound-o2", "unbound-o2-reference")
    repository.create(
        lifecycle,
        lifecycle.creation_transition(
            operator_id="system",
            reason="ADR-0065 unbound regression fixture",
        ),
    )
    try:
        with pytest.raises(
            VerifiedEconomicsAdmissionConflictError,
            match="missing or unsupported",
        ):
            FinalizeVerifiedEconomicsAdmission(repository).execute(
                _command(lifecycle.opportunity_id)
            )
    finally:
        repository.close()


def test_dual_market_and_target_binding_fails_as_conflict(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteValidationQueueRepository(path)
    source_market_binding = repository.get_market_identity_binding("opportunity-v2-1")
    repository.get_market_identity_binding = lambda _: source_market_binding
    try:
        with pytest.raises(
            VerifiedEconomicsAdmissionConflictError,
            match="conflicting operational binding variants",
        ):
            FinalizeVerifiedEconomicsAdmission(repository).execute(
                _command(publication.lifecycle.opportunity_id)
            )
    finally:
        repository.close()


def test_corrupt_target_binding_is_bounded_persistence_unavailable(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteValidationQueueRepository(path)
    repository._connection.execute(
        "DROP TRIGGER "
        "trg_opportunity_domestic_selling_target_bindings_no_update"
    )
    repository._connection.execute(
        "UPDATE opportunity_domestic_selling_target_bindings "
        "SET discovery_reference='corrupt-reference' WHERE opportunity_id=?",
        (publication.lifecycle.opportunity_id,),
    )
    repository._connection.commit()
    try:
        with pytest.raises(VerifiedEconomicsAdmissionPersistenceError):
            FinalizeVerifiedEconomicsAdmission(repository).execute(
                _command(publication.lifecycle.opportunity_id)
            )
    finally:
        repository.close()


def test_exact_replay_skips_current_subject_reads_and_changed_payload_conflicts(
    tmp_path,
):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteValidationQueueRepository(path)
    owner = FinalizeVerifiedEconomicsAdmission(repository)
    command = _command(publication.lifecycle.opportunity_id)
    first = owner.execute(command)
    repository.get = lambda _: pytest.fail("lifecycle must not be read during replay")
    repository.get_market_identity_binding = lambda _: pytest.fail(
        "Market binding must not be read during replay"
    )
    repository.get_target_binding = lambda _: pytest.fail(
        "target binding must not be read during replay"
    )
    try:
        replay = owner.execute(command)
        assert replay.snapshot == first.snapshot
        assert replay.replayed is True
        with pytest.raises(VerifiedEconomicsAdmissionConflictError):
            owner.execute(
                replace(
                    command,
                    inputs=_with_sale_price("334.00", "changed-target-price"),
                )
            )
    finally:
        repository.close()


def test_existing_snapshot_uniqueness_is_unchanged_for_target_o2(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteValidationQueueRepository(path)
    owner = FinalizeVerifiedEconomicsAdmission(repository)
    try:
        owner.execute(_command(publication.lifecycle.opportunity_id))
        with pytest.raises(
            VerifiedEconomicsAdmissionConflictError,
            match="snapshot already exists",
        ):
            owner.execute(
                _command(
                    publication.lifecycle.opportunity_id,
                    command_id="different-target-command",
                )
            )
    finally:
        repository.close()
