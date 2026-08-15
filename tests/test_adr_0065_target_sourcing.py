from dataclasses import replace
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.sourcing import (
    NewToMarketDomesticSellingProductLineageReference,
    SourcingAdmissionNotFoundError,
    SourcingAdmissionReplayConflictError,
    SourcingDomesticSellingLineageError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import NewToMarketDomesticSellingTargetIdentity
from app.domain.sourcing import (
    MatchVerificationStatus,
    NewToMarketDomesticSellingProductLineage,
    ProductMatchVerification,
)
from app.infrastructure.sourcing import (
    MalformedSourcingAuthorityPersistenceError,
    SQLiteSourcingAuthorityRepository,
    SourcingAuthorityPersistenceError,
)
from app.web import app
from test_adr_0065_target_sourcing_economics_ingress import (
    _target_sourcing_payload,
)
from test_new_to_market_competition_demand_target_support import _target_o2
from test_sourcing_authority_contract import (
    NOW,
    command as sourcing_command,
    evidence,
    service,
)
from test_sourcing_authority_sqlite_persistence import boundary


def _lineage(**changes):
    values = {
        "opportunity_identity": OpportunityIdentity(
            "new-market-o2-1",
            "new-to-market-domestic-selling:new-market-admission-1",
        ),
        "new_to_market_domestic_selling_admission_id": "new-market-admission-1",
        "target_identity": NewToMarketDomesticSellingTargetIdentity(
            "new-market-target-1"
        ),
    }
    values.update(changes)
    return NewToMarketDomesticSellingProductLineage(**values)


def _reference_command(publication, **changes):
    return sourcing_command(
        selling_product_lineage=(
            NewToMarketDomesticSellingProductLineageReference(
                publication.admission.admission_id
            )
        ),
        **changes,
    )


def test_target_lineage_has_only_exact_adr_0060_subject_facts():
    lineage = _lineage()

    assert lineage.opportunity_identity.opportunity_id == "new-market-o2-1"
    assert lineage.new_to_market_domestic_selling_admission_id == (
        "new-market-admission-1"
    )
    assert lineage.target_identity.domestic_selling_target_id == "new-market-target-1"
    assert lineage.schema_version == (
        "new-to-market-domestic-selling-product-lineage-v1"
    )
    for field in (
        "market_observation_identity",
        "source_opportunity_identity",
        "source_product_observation_snapshot_id",
        "product_equivalence_evidence_reference",
        "bound_at",
    ):
        assert not hasattr(lineage, field)


@pytest.mark.parametrize(
    ("change", "error"),
    (
        ({"opportunity_identity": "o2"}, TypeError),
        ({"new_to_market_domestic_selling_admission_id": " "}, ValueError),
        ({"target_identity": "target"}, TypeError),
    ),
)
def test_target_lineage_requires_exact_typed_authority_facts(change, error):
    with pytest.raises(error):
        _lineage(**change)


def test_product_match_accepts_target_lineage_without_changing_match_authority():
    lineage = _lineage()
    match = ProductMatchVerification(
        "match-target-1",
        lineage,
        "sourcing-product-1",
        MatchVerificationStatus.VERIFIED_MATCH,
        "founder-1",
        NOW,
        evidence(),
    )

    assert match.selling_product_lineage == lineage
    assert match.sourcing_product_id == "sourcing-product-1"
    assert match.schema_version == "sourcing-product-match-v1"


def test_exact_reference_reconstructs_target_lineage_and_round_trips(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
    try:
        result = boundary(repository).execute(_reference_command(publication))
        restored = repository.get_admission(result.admission.admission_id)
    finally:
        repository.close()

    lineage = result.admission.selling_product_lineage
    assert isinstance(lineage, NewToMarketDomesticSellingProductLineage)
    assert lineage.opportunity_identity == publication.admission.domestic_opportunity_identity
    assert lineage.target_identity == publication.admission.target_identity
    assert lineage.new_to_market_domestic_selling_admission_id == (
        publication.admission.admission_id
    )
    assert result.admission.schema_version == "founder-sourcing-admission-v4"
    assert restored == result.admission
    assert restored.match_verification.selling_product_lineage == lineage


def test_founder_admission_rejects_mixed_target_lineage_or_sourcing_product(
    tmp_path,
):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
    try:
        admission = boundary(repository).execute(
            _reference_command(publication)
        ).admission
    finally:
        repository.close()

    wrong_lineage = replace(
        admission.selling_product_lineage,
        target_identity=NewToMarketDomesticSellingTargetIdentity("wrong-target"),
    )
    wrong_match = replace(
        admission.match_verification,
        selling_product_lineage=wrong_lineage,
    )
    with pytest.raises(ValueError, match="preserve selling Product lineage"):
        replace(admission, match_verification=wrong_match)

    wrong_product_match = replace(
        admission.match_verification,
        sourcing_product_id="wrong-sourcing-product",
    )
    with pytest.raises(ValueError, match="reference Sourcing Product"):
        replace(admission, match_verification=wrong_product_match)


def test_full_target_lineage_with_wrong_o2_is_rejected_before_identity_generation(
    tmp_path,
):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
    boundary_service, _, suppliers = service(repository)
    wrong = NewToMarketDomesticSellingProductLineage(
        OpportunityIdentity("wrong-o2", "wrong-discovery"),
        publication.admission.admission_id,
        publication.admission.target_identity,
    )
    try:
        with pytest.raises(SourcingDomesticSellingLineageError):
            boundary_service.execute(
                sourcing_command(selling_product_lineage=wrong)
            )
        assert all(value.calls == 0 for value in suppliers)
    finally:
        repository.close()


def test_exact_reference_never_selects_another_or_latest_admission(tmp_path):
    path, _ = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
    boundary_service, _, suppliers = service(repository)
    try:
        with pytest.raises(SourcingAdmissionNotFoundError):
            boundary_service.execute(
                sourcing_command(
                    selling_product_lineage=(
                        NewToMarketDomesticSellingProductLineageReference(
                            "missing-exact-admission"
                        )
                    )
                )
            )
        assert all(value.calls == 0 for value in suppliers)
    finally:
        repository.close()


def test_corrupt_target_binding_fails_closed_before_identity_generation(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
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
    boundary_service, _, suppliers = service(repository)
    try:
        with pytest.raises(SourcingAuthorityPersistenceError):
            boundary_service.execute(_reference_command(publication))
        assert all(value.calls == 0 for value in suppliers)
    finally:
        repository.close()


def test_target_payload_fingerprint_corruption_fails_closed(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
    result = boundary(repository).execute(_reference_command(publication))
    repository._connection.execute(
        "DROP TRIGGER trg_founder_sourcing_admission_history_no_update"
    )
    row = repository._connection.execute(
        "SELECT payload_json FROM founder_sourcing_admission_history "
        "WHERE admission_id=?",
        (result.admission.admission_id,),
    ).fetchone()
    payload = json.loads(row[0])
    payload["selling_product_lineage"]["target_identity"][
        "domestic_selling_target_id"
    ] = "corrupt-target"
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert hashlib.sha256(encoded.encode("utf-8")).hexdigest() != (
        repository._connection.execute(
            "SELECT payload_fingerprint FROM founder_sourcing_admission_history "
            "WHERE admission_id=?",
            (result.admission.admission_id,),
        ).fetchone()[0]
    )
    repository._connection.execute(
        "UPDATE founder_sourcing_admission_history SET payload_json=? "
        "WHERE admission_id=?",
        (encoded, result.admission.admission_id),
    )
    repository._connection.commit()
    try:
        with pytest.raises(MalformedSourcingAuthorityPersistenceError):
            repository.get_admission(result.admission.admission_id)
    finally:
        repository.close()


def test_restart_replay_skips_adr_0060_source_and_changed_reference_conflicts(
    tmp_path,
):
    path, publication = _target_o2(tmp_path)
    command = _reference_command(publication)
    repository = SQLiteSourcingAuthorityRepository(path)
    first = boundary(repository).execute(command)
    repository.close()

    restarted = SQLiteSourcingAuthorityRepository(path)
    restarted.get_new_to_market_domestic_selling_admission = lambda _: pytest.fail(
        "ADR-0060 source must not be read during replay"
    )
    try:
        replay = boundary(restarted, fail=True).execute(command)
        assert replay.admission == first.admission
        assert replay.replayed is True
        changed = replace(
            command,
            selling_product_lineage=(
                NewToMarketDomesticSellingProductLineageReference(
                    "changed-exact-admission"
                )
            ),
        )
        with pytest.raises(SourcingAdmissionReplayConflictError):
            boundary(restarted, fail=True).execute(changed)
    finally:
        restarted.close()


def test_target_sourcing_history_remains_append_only(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteSourcingAuthorityRepository(path)
    boundary(repository).execute(_reference_command(publication))
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(
                "UPDATE founder_sourcing_admission_history SET revision=revision"
            )
    finally:
        repository._connection.rollback()
        repository.close()


@pytest.mark.parametrize(
    "extra",
    (
        {"target_identity": {"domestic_selling_target_id": "caller-target"}},
        {"domestic_selling_target_id": "caller-target"},
        {"discovery_reference": "caller-reference"},
        {"market_observation_identity": {"market": "KR"}},
    ),
)
def test_target_sourcing_api_rejects_caller_created_subject_facts(
    tmp_path,
    monkeypatch,
    extra,
):
    path, publication = _target_o2(tmp_path)
    body = _target_sourcing_payload(publication.admission.admission_id)
    body["selling_product_lineage"].update(extra)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/sourcing/admissions", json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
