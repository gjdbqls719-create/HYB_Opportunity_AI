from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from app.application.sourcing import (
    BindSourcingEconomicsSource,
    SourcingAdmissionReplayConflictError,
    SourcingDomesticSellingLineageError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import DomesticSellingProductLineage, MatchVerificationStatus
from app.infrastructure.domestic_selling_opportunity import (
    SQLiteDomesticSellingOpportunityAdmissionRepository,
)
from app.infrastructure.sourcing import SQLiteSourcingAuthorityRepository
from app.infrastructure.sourcing import SQLiteSourcingEconomicsBindingRepository
from test_domestic_selling_opportunity_admission import command as domestic_command
from test_domestic_selling_opportunity_sqlite import make_owner, seed
from test_sourcing_authority_contract import command as sourcing_command, service
from test_sourcing_authority_contract import NOW
from test_sourcing_economics_binding import Counter, binding_command


def prepare_domestic(path):
    seed(path)
    domestic_repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    publication = make_owner(domestic_repository).execute(domestic_command())
    domestic_repository.close()
    admission = publication.admission
    return publication, DomesticSellingProductLineage(
        opportunity_identity=admission.domestic_opportunity_identity,
        domestic_selling_admission_id=admission.admission_id,
        source_opportunity_identity=admission.source_opportunity_identity,
        source_product_observation_snapshot_id=admission.source_product_snapshot_id,
        market_observation_identity=admission.domestic_market_identity,
        product_equivalence_evidence_reference=(
            admission.product_equivalence.evidence_reference
        ),
    )


def test_exact_domestic_admission_creates_normal_sourcing_admission_owned_by_o2(tmp_path):
    path = tmp_path / "domestic-sourcing.db"
    publication, lineage = prepare_domestic(path)
    repository = SQLiteSourcingAuthorityRepository(path)

    result = service(repository)[0].execute(
        sourcing_command(selling_product_lineage=lineage)
    )

    assert result.admission.selling_product_lineage == lineage
    assert result.admission.selling_product_lineage.opportunity_identity == (
        publication.admission.domestic_opportunity_identity
    )
    assert result.admission.selling_product_lineage.source_opportunity_identity == (
        publication.admission.source_opportunity_identity
    )
    assert result.admission.match_verification.status is MatchVerificationStatus.VERIFIED_MATCH
    assert result.admission.schema_version == "founder-sourcing-admission-v3"
    repository.close()


def test_domestic_admission_does_not_replace_supplier_product_match(tmp_path):
    path = tmp_path / "match.db"
    _, lineage = prepare_domestic(path)
    repository = SQLiteSourcingAuthorityRepository(path)
    with pytest.raises(Exception, match="verified match"):
        service(repository)[0].execute(
            sourcing_command(
                selling_product_lineage=lineage,
                match_status=MatchVerificationStatus.NEEDS_REVIEW,
            )
        )
    repository.close()


@pytest.mark.parametrize(
    "change",
    (
        {"domestic_selling_admission_id": "missing-admission"},
        {"opportunity_identity": OpportunityIdentity("wrong-o2", "wrong-reference")},
        {"source_opportunity_identity": OpportunityIdentity("wrong-o1", "wrong-source")},
        {"source_product_observation_snapshot_id": "wrong-snapshot"},
        {"product_equivalence_evidence_reference": "wrong-evidence"},
    ),
)
def test_missing_or_mixed_domestic_lineage_is_rejected_before_identity(tmp_path, change):
    path = tmp_path / "wrong.db"
    _, lineage = prepare_domestic(path)
    repository = SQLiteSourcingAuthorityRepository(path)
    boundary, _, suppliers = service(repository)
    with pytest.raises(SourcingDomesticSellingLineageError):
        boundary.execute(sourcing_command(selling_product_lineage=replace(lineage, **change)))
    assert all(value.calls == 0 for value in suppliers)
    repository.close()


def test_domestic_lineage_is_immutable_and_cannot_carry_candidate_fields(tmp_path):
    _, lineage = prepare_domestic(tmp_path / "immutable.db")
    with pytest.raises(FrozenInstanceError):
        lineage.domestic_selling_admission_id = "changed"
    assert not hasattr(lineage, "candidate_id")
    assert not hasattr(lineage, "candidate_opportunity_binding_id")


def test_domestic_sourcing_replay_restart_and_changed_lineage_conflict(tmp_path):
    path = tmp_path / "restart.db"
    _, lineage = prepare_domestic(path)
    repository = SQLiteSourcingAuthorityRepository(path)
    first = service(repository)[0].execute(
        sourcing_command(selling_product_lineage=lineage)
    )
    repository.close()

    repository = SQLiteSourcingAuthorityRepository(path)
    replay = service(repository)[0].execute(
        sourcing_command(selling_product_lineage=lineage)
    )
    assert replay == replace(first, replayed=True)
    with pytest.raises(SourcingAdmissionReplayConflictError):
        service(repository)[0].execute(
            sourcing_command(
                selling_product_lineage=replace(
                    lineage,
                    product_equivalence_evidence_reference="changed-reference",
                )
            )
        )
    repository.close()


def test_legacy_candidate_lineage_round_trip_remains_unchanged(tmp_path):
    path = tmp_path / "legacy.db"
    repository = SQLiteSourcingAuthorityRepository(path)
    first = service(repository)[0].execute(sourcing_command())
    repository.close()
    repository = SQLiteSourcingAuthorityRepository(path)
    assert repository.get_admission(first.admission.admission_id) == first.admission
    assert first.admission.schema_version == "founder-sourcing-admission-v2"
    repository.close()


def test_existing_sourcing_economics_binding_consumes_o2_admission_without_o1_logic(tmp_path):
    path = tmp_path / "binding.db"
    publication, lineage = prepare_domestic(path)
    sourcing = SQLiteSourcingAuthorityRepository(path)
    admission = service(sourcing)[0].execute(
        sourcing_command(selling_product_lineage=lineage)
    ).admission
    sourcing.close()

    bindings = SQLiteSourcingEconomicsBindingRepository(path)
    result = BindSourcingEconomicsSource(
        bindings,
        binding_id_generator=Counter("o2-binding"),
        bound_clock=Counter(NOW + timedelta(minutes=1)),
        committed_clock=Counter(NOW + timedelta(minutes=2)),
    ).execute(
        binding_command(
            admission,
            opportunity_identity=publication.admission.domestic_opportunity_identity,
        )
    )
    assert result.binding.opportunity_identity == (
        publication.admission.domestic_opportunity_identity
    )
    assert result.binding.source_reference == admission.to_economics_source_reference()
    bindings.close()
