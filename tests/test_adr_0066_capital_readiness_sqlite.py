from dataclasses import replace
from datetime import timedelta
import hashlib
import json

import pytest

from app.application.capital_readiness import (
    EvaluateCapitalReadiness,
    EvaluateCapitalReadinessCommandV2,
)
from app.application.domestic_market_validation_v2 import (
    PersistDomesticMarketValidationV2ForCapital,
    ValidateDomesticMarketV2Command,
    ValidateDomesticMarketV2ForCapital,
)
from app.application.sourcing import (
    NewToMarketDomesticSellingProductLineageReference,
)
from app.domain.capital import (
    DomesticMarketValidationSourceKind,
    DomesticMarketValidationSourceReference,
)
from app.domain.market_intelligence.domestic_market_validation_v2 import (
    DomesticMarketVerificationV2,
)
from app.infrastructure.capital_readiness import (
    MalformedCapitalReadinessPersistenceError,
    SQLiteCapitalReadinessRepository,
)
from app.infrastructure.domestic_market_validation_v2 import (
    SQLiteDomesticMarketValidationV2Repository,
)
from app.infrastructure.new_to_market_domestic_selling import (
    SQLiteNewToMarketDomesticSellingAdmissionRepository,
)
from test_capital_readiness import Calls, verified_economics
import test_capital_readiness_sqlite as v1
from test_domestic_market_validation_v2 import (
    EVALUATED_AT,
    Repository as DmvSourceRepository,
    VERIFIED_AT,
    _competition_publication,
    _demand_publication,
)
from test_new_to_market_competition_demand_target_support import _target_o2
from test_sourcing_authority_contract import NOW, command as sourcing_command
from test_sourcing_authority_sqlite_persistence import boundary as sourcing_boundary


def _persist_target_dmv(database, target_binding):
    competition, fingerprint = _competition_publication(
        subject=target_binding.target_identity
    )
    demand = _demand_publication(subject=target_binding.target_identity)
    competition = replace(
        competition,
        opportunity_id=target_binding.opportunity_id,
    )
    demand = replace(
        demand,
        opportunity_id=target_binding.opportunity_id,
    )

    class SourceRepository(DmvSourceRepository):
        def get_target_binding(self, opportunity_id):
            return (
                self.target_binding
                if opportunity_id == self.target_binding.opportunity_id
                else None
            )

    source = SourceRepository(
        competition,
        demand,
        target_binding=target_binding,
        competition_fingerprint=fingerprint,
    )
    owner = ValidateDomesticMarketV2ForCapital(
        source,
        assessment_id_generator=lambda: "dmv-v2-assessment-target-1",
        evaluated_clock=lambda: EVALUATED_AT,
    )
    manifest = owner.resolve_source_manifest(
        target_binding.opportunity_id,
        competition.observation_id,
        demand.observation.observation_id,
    )
    command = ValidateDomesticMarketV2Command(
        command_id="dmv-v2-command-target-1",
        opportunity_id=target_binding.opportunity_id,
        competition_observation_id=competition.observation_id,
        demand_observation_id=demand.observation.observation_id,
        verification=DomesticMarketVerificationV2(
            operator_id="founder",
            verified_at=VERIFIED_AT,
            current_use_confirmed=True,
            reviewed_source_manifest_fingerprint=manifest.fingerprint,
        ),
        requested_at=VERIFIED_AT,
    )
    repository = SQLiteDomesticMarketValidationV2Repository(database)
    try:
        return PersistDomesticMarketValidationV2ForCapital(
            repository,
            owner,
            committed_clock=lambda: EVALUATED_AT + timedelta(minutes=1),
        ).execute(command).assessment
    finally:
        repository.close()


def seed_target_sources(tmp_path):
    database, target_publication = _target_o2(tmp_path)
    opportunity = target_publication.admission.domestic_opportunity_identity
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(database)
    try:
        target_binding = repository.get_target_binding(opportunity.opportunity_id)
    finally:
        repository.close()
    assert target_binding is not None

    base = sourcing_command()
    sourcing = sourcing_command(
        selling_product_lineage=(
            NewToMarketDomesticSellingProductLineageReference(
                target_publication.admission.admission_id
            )
        ),
        shipping_terms=tuple(
            v1.ShippingTerm(
                term.scope,
                v1.SourcingMoneyFact(
                    v1.CommercialFactAvailability.NOT_APPLICABLE
                ),
            )
            for term in base.shipping_terms
        ),
        quote_valid_until=NOW + timedelta(days=30),
    )
    with v1.SQLiteSourcingAuthorityRepository(database) as repository:
        admission = sourcing_boundary(repository).execute(sourcing).admission
    with v1.SQLiteSourcingEconomicsBindingRepository(database) as repository:
        binding = v1.BindSourcingEconomicsSource(
            repository,
            binding_id_generator=lambda: "binding-target-1",
            bound_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(
            v1.BindSourcingEconomicsSourceCommand(
                "binding-command-target-1",
                opportunity,
                admission.to_economics_source_reference(),
                NOW,
            )
        ).binding
    with v1.SQLiteLandedCostCompositionRepository(database) as repository:
        landed = v1.ComposeLandedCost(
            repository,
            composition_id_generator=lambda: "landed-composition-target-1",
            composed_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(
            v1.ComposeLandedCostCommand(
                "landed-command-target-1",
                opportunity,
                binding.reference,
                NOW,
            )
        ).composition
    with v1.SQLiteAcquisitionCostNormalizationRepository(database) as repository:
        normalization = v1.NormalizeAcquisitionCosts(
            repository,
            normalization_id_generator=lambda: "normalization-target-1",
            normalized_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(
            v1.normalization_command(
                landed,
                (),
                (),
                target_currency="CNY",
                allocation_authority_ids=(),
                fx_observation_ids=(),
            )
        ).normalization

    verified = v1.VerifiedEconomicsSnapshot(
        opportunity.opportunity_id,
        verified_economics(),
        NOW,
    )
    queue = v1.SQLiteValidationQueueRepository(database)
    queue._insert_verified_economics_snapshot(verified)
    queue._connection.commit()
    queue.close()

    with v1.SQLiteEconomicsSourceCompositionRepository(database) as repository:
        source = v1.ComposeEconomicsSources(
            repository,
            composition_id_generator=lambda: "economics-source-target-1",
            composed_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(v1.source_command(normalization, verified)).composition
    with v1.SQLiteConservativeEconomicsRepository(database) as repository:
        conservative = v1.EvaluateConservativeEconomics(
            repository,
            result_id_generator=lambda: "conservative-result-target-1",
            calculated_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(v1.conservative_command(source)).result
    with v1.SQLiteCriticalCostCompletenessRepository(database) as repository:
        critical = v1.critical_owner(
            repository,
            policy=v1.DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        )[0].execute(
            v1.persistence_command(
                landed,
                verified,
                normalization=normalization,
                policy=v1.DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
            )
        ).assessment
    market = _persist_target_dmv(database, target_binding)
    return database, opportunity, conservative, critical, market


def _command(opportunity, conservative, critical, market):
    return EvaluateCapitalReadinessCommandV2(
        command_id="capital-readiness-command-target-1",
        opportunity_id=opportunity.opportunity_id,
        conservative_economics_result_id=conservative.result_id,
        domestic_market_validation_source=DomesticMarketValidationSourceReference(
            DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V2,
            market.assessment_id,
        ),
        critical_cost_assessment_id="critical-cost-assessment-1",
        requested_at=NOW,
    )


def _owner(repository, *, fail=False):
    def supplier(value, message):
        if not fail:
            return Calls(value)

        def rejected():
            raise AssertionError(message)

        return rejected

    return EvaluateCapitalReadiness(
        repository,
        assessment_id_generator=supplier(
            "capital-readiness-target-1",
            "identity called during replay",
        ),
        evaluated_clock=supplier(
            NOW,
            "evaluated clock called during replay",
        ),
        committed_clock=supplier(
            NOW,
            "committed clock called during replay",
        ),
    )


def test_v3_round_trip_uses_existing_tables_and_preserves_exact_v2_pins(tmp_path):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    command = _command(opportunity, conservative, critical, market)
    with SQLiteCapitalReadinessRepository(database) as repository:
        publication = _owner(repository).execute(command)
        columns = tuple(
            row[1]
            for row in repository._connection.execute(
                "PRAGMA table_info(capital_readiness_history)"
            ).fetchall()
        )
        receipt_columns = tuple(
            row[1]
            for row in repository._connection.execute(
                "PRAGMA table_info(capital_readiness_receipts)"
            ).fetchall()
        )

    with SQLiteCapitalReadinessRepository(database) as repository:
        restored = repository.get_assessment(publication.assessment.assessment_id)
        v1_rows = repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_history"
        ).fetchone()[0]

    assert restored == publication.assessment
    assert columns == (
        "assessment_id",
        "opportunity_id",
        "discovery_reference",
        "conservative_result_id",
        "market_validation_assessment_id",
        "critical_cost_assessment_id",
        "state",
        "policy_name",
        "policy_version",
        "payload_json",
        "integrity_fingerprint",
        "schema_version",
        "inserted_at",
    )
    assert receipt_columns == (
        "command_id",
        "assessment_id",
        "command_fingerprint",
        "committed_at",
        "schema_version",
        "inserted_at",
    )
    assert v1_rows == 0
    assert restored.source_manifest.domestic_market_validation_assessment_id == (
        market.assessment_id
    )
    assert (
        restored.source_manifest.domestic_market_validation_source_manifest_fingerprint
        == market.source_manifest_fingerprint
    )
    assert not hasattr(restored.source_manifest, "target_identity")


def test_v3_restart_replay_does_not_read_any_exact_source(tmp_path):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    command = _command(opportunity, conservative, critical, market)
    with SQLiteCapitalReadinessRepository(database) as repository:
        original = _owner(repository).execute(command)

    with SQLiteCapitalReadinessRepository(database) as repository:
        def fail(*_args, **_kwargs):
            raise AssertionError("exact source read during v3 replay")

        for name in (
            "get_conservative_economics_result",
            "get_economics_source_composition",
            "get_acquisition_normalization",
            "get_critical_cost_assessment",
            "get_domestic_market_validation",
            "get_domestic_market_validation_v2",
            "get_sourcing_binding",
            "get_sourcing_admission",
        ):
            setattr(repository, name, fail)
        replay = _owner(repository, fail=True).execute(command)
        counts = tuple(
            repository._connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in (
                "capital_readiness_history",
                "capital_readiness_receipts",
            )
        )

    assert replay.replayed is True
    assert replay.assessment == original.assessment
    assert replay.receipt == original.receipt
    assert counts == (1, 1)


def test_blocked_assessment_v3_round_trip_is_exact(tmp_path):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    command = replace(
        _command(opportunity, conservative, critical, market),
        opportunity_id="different-route-opportunity",
    )
    with SQLiteCapitalReadinessRepository(database) as repository:
        publication = _owner(repository).execute(command)

    with SQLiteCapitalReadinessRepository(database) as repository:
        restored = repository.get_assessment(publication.assessment.assessment_id)

    assert publication.assessment.state.value == "blocked"
    assert restored == publication.assessment


def test_v3_payload_fingerprint_corruption_fails_closed_on_source_free_replay(
    tmp_path,
):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    command = _command(opportunity, conservative, critical, market)
    with SQLiteCapitalReadinessRepository(database) as repository:
        publication = _owner(repository).execute(command)
        repository._connection.execute(
            "DROP TRIGGER trg_capital_readiness_history_no_update"
        )
        row = repository._connection.execute(
            "SELECT payload_json FROM capital_readiness_history WHERE assessment_id=?",
            (publication.assessment.assessment_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["source_manifest"][
            "domestic_market_validation_source_manifest_fingerprint"
        ] = "0" * 64
        repository._connection.execute(
            "UPDATE capital_readiness_history SET payload_json=? WHERE assessment_id=?",
            (json.dumps(payload), publication.assessment.assessment_id),
        )
        repository._connection.commit()

    with SQLiteCapitalReadinessRepository(database) as repository:
        with pytest.raises(MalformedCapitalReadinessPersistenceError):
            _owner(repository, fail=True).execute(command)


def test_normal_read_rejects_persisted_dmv_v2_manifest_fingerprint_mismatch(
    tmp_path,
):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    command = _command(opportunity, conservative, critical, market)
    with SQLiteCapitalReadinessRepository(database) as repository:
        publication = _owner(repository).execute(command)
        repository._connection.execute(
            "DROP TRIGGER trg_capital_readiness_history_no_update"
        )
        row = repository._connection.execute(
            "SELECT payload_json FROM capital_readiness_history WHERE assessment_id=?",
            (publication.assessment.assessment_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["source_manifest"][
            "domestic_market_validation_source_manifest_fingerprint"
        ] = "0" * 64
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        repository._connection.execute(
            "UPDATE capital_readiness_history "
            "SET payload_json=?,integrity_fingerprint=? WHERE assessment_id=?",
            (
                encoded,
                hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                publication.assessment.assessment_id,
            ),
        )
        repository._connection.commit()

    with SQLiteCapitalReadinessRepository(database) as repository:
        with pytest.raises(MalformedCapitalReadinessPersistenceError):
            repository.get_assessment(publication.assessment.assessment_id)


@pytest.mark.parametrize(
    "case",
    ("assessment_id", "opportunity_id", "terminal_source"),
)
def test_v3_row_and_payload_identity_mismatches_fail_closed(tmp_path, case):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    command = _command(opportunity, conservative, critical, market)
    with SQLiteCapitalReadinessRepository(database) as repository:
        publication = _owner(repository).execute(command)
        repository._connection.execute(
            "DROP TRIGGER trg_capital_readiness_history_no_update"
        )
        row = repository._connection.execute(
            "SELECT payload_json FROM capital_readiness_history WHERE assessment_id=?",
            (publication.assessment.assessment_id,),
        ).fetchone()
        payload = json.loads(row[0])
        if case == "assessment_id":
            payload["assessment_id"] = "different-assessment"
        elif case == "opportunity_id":
            payload["source_manifest"]["opportunity_identity"][
                "opportunity_id"
            ] = "different-opportunity"
        else:
            payload["source_manifest"][
                "conservative_economics_result_id"
            ] = "different-conservative-result"
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        repository._connection.execute(
            "UPDATE capital_readiness_history "
            "SET payload_json=?,integrity_fingerprint=? WHERE assessment_id=?",
            (
                encoded,
                hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                publication.assessment.assessment_id,
            ),
        )
        repository._connection.commit()

    with SQLiteCapitalReadinessRepository(database) as repository:
        with pytest.raises(MalformedCapitalReadinessPersistenceError):
            repository.get_assessment(publication.assessment.assessment_id)
