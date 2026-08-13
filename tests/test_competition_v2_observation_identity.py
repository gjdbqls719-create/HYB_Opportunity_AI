from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

import app.application.competition_v2_admission as admission_module
from app.application.competition_v2_admission import (
    CompetitionV2AdmissionConflictError,
    CompetitionV2AdmissionResult,
    CompetitionV2AdmissionUnavailableError,
    FinalizeCompetitionV2Admission,
    FinalizeCompetitionV2AdmissionCommand,
)
from app.domain.market_intelligence.competition_v2 import (
    COMPETITION_V2_LEGACY_OBSERVATION_IDENTITY_VERSION,
    COMPETITION_V2_OBSERVATION_IDENTITY_VERSION,
    CompetitionV2Card,
    CompetitionV2Cohort,
    CompetitionV2ObservationIdentityKind,
    ResultPlacement,
    RocketObservationOutcome,
    legacy_competition_v2_observation_identity,
)
from app.domain.opportunity.new_to_market_domestic_selling import (
    NewToMarketDomesticSellingTargetIdentity,
)
from app.infrastructure.market_observation.competition_v2_sqlite_repository import (
    CompetitionV2CorruptionError,
    SQLiteCompetitionV2Repository,
)
from app.web import _competition_v2_payload, app


NOW = datetime(2026, 8, 13, 6, tzinfo=timezone.utc)
HASH = "a" * 64


def _target(): return NewToMarketDomesticSellingTargetIdentity("identity-target")


def _cohort(cohort_id="identity-cohort-1", price="100"):
    return CompetitionV2Cohort(
        cohort_id=cohort_id, subject=_target(), market="KR", marketplace="coupang",
        query="seat organizer", category="car accessories", product_use="seat-back storage",
        category_form_factor="organizer", condition="new", locale="ko-KR",
        result_surface="coupang-search", window_started_at=NOW, window_ended_at=NOW,
        artifact_reference=f"artifact:{cohort_id}", artifact_sha256=HASH,
        bound_start=1, bound_end=1, operator_id="founder",
        cards=(CompetitionV2Card(
            result_ordinal=1, placement=ResultPlacement.ORGANIC, included=True,
            is_comparable=True, exclusion_reason=None, marketplace_item_id="item-1",
            raw_title="synthetic listing", displayed_price=Decimal(price), currency="KRW",
            price_unit="item", raw_rocket_labels=(), delivery_promise_text=None,
            rocket_outcome=RocketObservationOutcome.OBSERVED,
            comparability_confidence=Decimal("1"), price_confidence=Decimal("1"),
            rocket_label_confidence=Decimal("1"), visible_seller_text=None,
            visible_variant_count=1, raw_payload_reference=None, badge_color=None,
            badge_icon=None),))


def _command(cohort=None, command_id="identity-command-1"):
    return FinalizeCompetitionV2AdmissionCommand(
        "identity-opportunity", command_id, "founder", NOW, cohort or _cohort()
    )


def _eligibility(monkeypatch):
    value = SimpleNamespace(
        market_binding=None, target_binding=SimpleNamespace(target_identity=_target())
    )
    monkeypatch.setattr(
        admission_module, "get_operational_opportunity_eligibility",
        lambda repository, opportunity_id: value,
    )


def _service(repository, generated, clock=lambda: NOW):
    return FinalizeCompetitionV2Admission(
        object(), repository, clock=clock,
        observation_id_generator=lambda: generated.append(1) or "issued-observation-1",
    )


def test_legacy_compatibility_identity_has_exact_stable_vector():
    identity = legacy_competition_v2_observation_identity("legacy-cohort-1", HASH)
    assert identity.observation_id == (
        "legacy-competition-v2-observation-v1:"
        "054140d1e0b3a7a333fa85080e7e839065022c865cf73de1aec3d7ebbe8470f9"
    )
    assert identity.identity_kind is CompetitionV2ObservationIdentityKind.LEGACY_COMPATIBILITY
    assert identity.identity_version == COMPETITION_V2_LEGACY_OBSERVATION_IDENTITY_VERSION
    assert legacy_competition_v2_observation_identity("legacy-cohort-1", "b" * 64) != identity


def test_new_publication_replay_alias_restart_and_lookup_preserve_server_id(tmp_path, monkeypatch):
    _eligibility(monkeypatch); path = tmp_path / "current.sqlite3"
    repository = SQLiteCompetitionV2Repository(path); generated = []
    service = _service(repository, generated)
    first = service.execute(_command())
    replay = service.execute(_command())
    alias = service.execute(_command(command_id="identity-command-2"))
    identity = first.publication.observation_identity
    assert identity.observation_id == "issued-observation-1"
    assert identity.identity_kind is CompetitionV2ObservationIdentityKind.ISSUED
    assert identity.identity_version == COMPETITION_V2_OBSERVATION_IDENTITY_VERSION
    assert replay.publication.observation_identity == identity
    assert alias.publication.observation_identity == identity
    assert replay.replayed and alias.aliased and generated == [1]
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM competition_v2_observation_identities"
    ).fetchone()[0] == 1
    repository.close(); restarted = SQLiteCompetitionV2Repository(path)
    assert restarted.get_publication("identity-cohort-1").observation_identity == identity
    assert restarted.get_publication_by_observation_id(identity.observation_id).cohort.cohort_id == "identity-cohort-1"
    restarted.close()


def test_identity_constraints_and_transaction_rollback_prevent_orphans(tmp_path, monkeypatch):
    _eligibility(monkeypatch); repository = SQLiteCompetitionV2Repository(tmp_path / "atomic.sqlite3")
    first = _service(repository, []).execute(_command())
    duplicate_generator = []
    second = _service(repository, duplicate_generator)
    with pytest.raises(CompetitionV2AdmissionConflictError):
        second.execute(_command(_cohort("identity-cohort-2"), "identity-command-2"))
    assert repository.get_publication("identity-cohort-2") is None
    assert repository.get_publication_by_observation_id(first.publication.observation_id) == first.publication
    assert duplicate_generator == [1]
    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute(
            "INSERT INTO competition_v2_observation_identities VALUES (?,?,?,?,?)",
            ("other-observation", "identity-cohort-1", "issued",
             COMPETITION_V2_OBSERVATION_IDENTITY_VERSION, NOW.isoformat()),
        )
    repository._connection.rollback()
    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute(
            "UPDATE competition_v2_observation_identities SET observation_id=observation_id"
        )
    repository._connection.rollback(); repository.close()


def test_legacy_schema_read_is_byte_stable_replays_without_id_or_clock_and_rejects_writes(tmp_path, monkeypatch):
    _eligibility(monkeypatch); path = tmp_path / "legacy.sqlite3"
    repository = SQLiteCompetitionV2Repository(path); command = _command(); generated = []
    original_command_fingerprint = command.fingerprint()
    original_authority_fingerprint = command.authority_fingerprint()
    first = _service(repository, generated).execute(command)
    repository._connection.execute("DROP TRIGGER trg_competition_v2_observation_identities_no_update")
    repository._connection.execute("DROP TRIGGER trg_competition_v2_observation_identities_no_delete")
    repository._connection.execute("DROP TABLE competition_v2_observation_identities")
    repository._connection.commit(); repository.close()
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)
    legacy = SQLiteCompetitionV2Repository(path)
    assert legacy.schema_variant == "legacy"
    publication = legacy.get_publication(first.publication.cohort.cohort_id)
    assert publication.observation_identity.identity_kind is CompetitionV2ObservationIdentityKind.LEGACY_COMPATIBILITY
    assert legacy.get_publication_by_observation_id(publication.observation_id) == publication
    replay_service = FinalizeCompetitionV2Admission(
        object(), legacy,
        clock=lambda: (_ for _ in ()).throw(AssertionError("legacy replay called clock")),
        observation_id_generator=lambda: (_ for _ in ()).throw(AssertionError("legacy replay issued ID")),
    )
    assert replay_service.execute(command).publication == publication
    assert command.fingerprint() == original_command_fingerprint
    assert command.authority_fingerprint() == original_authority_fingerprint
    with pytest.raises(CompetitionV2AdmissionUnavailableError):
        replay_service.execute(_command(_cohort("new-legacy-cohort"), "new-legacy-command"))
    legacy.close()
    after = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)
    assert before == after


def test_missing_or_corrupt_current_identity_fails_closed(tmp_path, monkeypatch):
    _eligibility(monkeypatch); path = tmp_path / "corrupt.sqlite3"
    repository = SQLiteCompetitionV2Repository(path)
    result = _service(repository, []).execute(_command())
    repository._connection.execute("DROP TRIGGER trg_competition_v2_observation_identities_no_update")
    repository._connection.execute(
        "UPDATE competition_v2_observation_identities SET identity_version='wrong'"
    )
    repository._connection.commit()
    with pytest.raises(CompetitionV2CorruptionError):
        repository.get_publication(result.publication.cohort.cohort_id)
    repository.close()


def test_api_and_openapi_expose_identity_only_in_response(tmp_path, monkeypatch):
    _eligibility(monkeypatch); repository = SQLiteCompetitionV2Repository(tmp_path / "api.sqlite3")
    result = _service(repository, []).execute(_command())
    payload = _competition_v2_payload(result)
    assert payload["observation_id"] == "issued-observation-1"
    assert payload["observation_identity_kind"] == "issued"
    assert payload["observation_identity_version"] == COMPETITION_V2_OBSERVATION_IDENTITY_VERSION
    legacy_payload = _competition_v2_payload(CompetitionV2AdmissionResult(
        result.publication, replayed=True
    ))
    assert legacy_payload["cohort"] == payload["cohort"]
    assert legacy_payload["assessment"] == payload["assessment"]
    document = app.openapi(); schemas = document["components"]["schemas"]
    response_fields = schemas["CompetitionV2AdmissionResponse"]["properties"]
    assert {"observation_id", "observation_identity_kind", "observation_identity_version"} <= set(response_fields)
    for name in ("CompetitionV2HistoricalAdmissionRequest", "CompetitionV2TargetAdmissionRequest", "CompetitionV2CohortRequest"):
        assert "observation_id" not in schemas[name]["properties"]
    repository.close()
