from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

from app.application.capital_readiness import (
    CapitalReadinessReplayConflictError,
    EvaluateCapitalReadiness,
)
from app.application.conservative_economics import EvaluateConservativeEconomics
from app.application.domestic_market_validation import ValidateDomesticMarketForCapital
from app.application.economics_source_composition import ComposeEconomicsSources
from app.application.opportunity_validation import OpportunityValidationService
from app.application.sourcing import (
    BindSourcingEconomicsSource,
    BindSourcingEconomicsSourceCommand,
    ComposeLandedCost,
    ComposeLandedCostCommand,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
    NormalizeAcquisitionCosts,
    PersistCriticalCostCompleteness,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CommercialFactAvailability,
    ShippingTerm,
    SourcingMoneyFact,
)
from app.infrastructure.capital_readiness import (
    CapitalReadinessCommitError,
    CapitalReadinessHistoryError,
    CapitalReadinessReceiptError,
    MalformedCapitalReadinessPersistenceError,
    SQLiteCapitalReadinessRepository,
)
from app.infrastructure.conservative_economics import SQLiteConservativeEconomicsRepository
from app.infrastructure.domestic_market_validation import SQLiteDomesticMarketValidationRepository
from app.infrastructure.economics_source_composition import SQLiteEconomicsSourceCompositionRepository
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.sourcing import (
    SQLiteAcquisitionCostNormalizationRepository,
    SQLiteCriticalCostCompletenessRepository,
    SQLiteLandedCostCompositionRepository,
    SQLiteSourcingAuthorityRepository,
    SQLiteSourcingEconomicsBindingRepository,
)
from test_acquisition_cost_normalization import command as normalization_command
from test_capital_readiness import command as readiness_command
from test_capital_readiness import verified_economics
from test_conservative_economics import command as conservative_command
from test_critical_cost_completeness_sqlite import (
    owner as critical_owner,
    persistence_command,
)
from test_domestic_market_validation import (
    NOW as MARKET_NOW,
    command as market_command,
    competition,
    competition_snapshot,
    demand,
    demand_snapshot,
    identity as domestic_identity,
)
from test_economics_source_composition import command as source_command
from test_opportunity_market_identity_binding import command as validation_command
from test_sourcing_authority_contract import NOW, command as sourcing_command
from test_sourcing_authority_sqlite_persistence import boundary as sourcing_boundary


HISTORY = "capital_readiness_history"
RECEIPTS = "capital_readiness_receipts"


class Counter:
    def __init__(self, value, *, fail=False):
        self.value = value
        self.calls = 0
        self.fail = fail

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise AssertionError("fresh dependency called during replay")
        return self.value


def seed(path: Path):
    opportunity = OpportunityIdentity("opp-1", "discovery:1")
    market_identity = domestic_identity()
    base = sourcing_command()
    lineage = replace(
        base.selling_product_lineage,
        opportunity_identity=opportunity,
        market_observation_identity=market_identity,
    )
    sourcing = sourcing_command(
        selling_product_lineage=lineage,
        shipping_terms=tuple(
            ShippingTerm(
                term.scope,
                SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
            )
            for term in base.shipping_terms
        ),
        quote_valid_until=NOW + timedelta(days=30),
    )
    with SQLiteSourcingAuthorityRepository(path) as repository:
        admission = sourcing_boundary(repository).execute(sourcing).admission
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        binding = BindSourcingEconomicsSource(
            repository,
            binding_id_generator=lambda: "binding-1",
            bound_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(BindSourcingEconomicsSourceCommand(
            "binding-command-1",
            opportunity,
            admission.to_economics_source_reference(),
            NOW,
        )).binding
    with SQLiteLandedCostCompositionRepository(path) as repository:
        landed = ComposeLandedCost(
            repository,
            composition_id_generator=lambda: "landed-composition-1",
            composed_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(ComposeLandedCostCommand(
            "landed-command-1", opportunity, binding.reference, NOW
        )).composition
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        normalization = NormalizeAcquisitionCosts(
            repository,
            normalization_id_generator=lambda: "normalization-1",
            normalized_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(normalization_command(
            landed,
            (),
            (),
            target_currency="CNY",
            allocation_authority_ids=(),
            fx_observation_ids=(),
        )).normalization

    queue = SQLiteValidationQueueRepository(path)
    validation_request = replace(
        validation_command(market_identity),
        opportunity_id=opportunity.opportunity_id,
        discovery_reference=opportunity.discovery_reference,
        marketplace=market_identity.marketplace,
        currency="CNY",
    )
    OpportunityValidationService(
        queue_repository=queue,
        lifecycle_repository=queue,
    ).add(validation_request)
    verified = VerifiedEconomicsSnapshot(
        opportunity.opportunity_id,
        verified_economics(),
        NOW,
    )
    queue._insert_verified_economics_snapshot(verified)
    queue._connection.commit()
    queue.close()

    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        source = ComposeEconomicsSources(
            repository,
            composition_id_generator=lambda: "economics-source-1",
            composed_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(source_command(normalization, verified)).composition
    with SQLiteConservativeEconomicsRepository(path) as repository:
        conservative = EvaluateConservativeEconomics(
            repository,
            result_id_generator=lambda: "conservative-result-1",
            calculated_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(conservative_command(source)).result
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        critical = critical_owner(
            repository,
            policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        )[0].execute(
            persistence_command(
                landed,
                verified,
                normalization=normalization,
                policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
            )
        )

    observations = SQLiteMarketObservationRepository(path)
    comp = competition(market_identity)
    dem = demand(market_identity)
    observations.save_assessment_snapshot(comp, competition_snapshot(comp))
    observations.save_assessment_snapshot(dem, demand_snapshot(dem))
    observations.close()
    with SQLiteDomesticMarketValidationRepository(path) as repository:
        market = ValidateDomesticMarketForCapital(
            repository,
            assessment_id_generator=lambda: "market-validation-1",
            evaluated_clock=lambda: MARKET_NOW + timedelta(minutes=10),
            committed_clock=lambda: MARKET_NOW + timedelta(minutes=11),
        ).execute(market_command(
            identity_value=market_identity,
            opportunity_identity=opportunity,
        ))
    return opportunity, conservative, critical.assessment, market.assessment


def owner(repository, identity="capital-readiness-1", *, fail=False, evaluated_at=None):
    identity_calls = Counter(identity, fail=fail)
    evaluated = Counter(evaluated_at or NOW + timedelta(days=1), fail=fail)
    committed = Counter(NOW + timedelta(days=1, minutes=1), fail=fail)
    return (
        EvaluateCapitalReadiness(
            repository,
            assessment_id_generator=identity_calls,
            evaluated_clock=evaluated,
            committed_clock=committed,
        ),
        identity_calls,
        evaluated,
        committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def persisted_request(sources, opportunity, **changes):
    changes.setdefault(
        "critical_cost_assessment_id", "critical-cost-assessment-1"
    )
    return readiness_command(
        sources,
        opportunity,
        **changes,
    )


def test_round_trip_restart_replay_and_read_path_no_mutation(tmp_path: Path) -> None:
    path = tmp_path / "capital.sqlite3"
    opportunity, conservative, critical, market = seed(path)
    request = persisted_request(type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })(), opportunity)
    with SQLiteCapitalReadinessRepository(path) as repository:
        first = owner(repository)[0].execute(request)
        before = repository._connection.total_changes
        assert repository.get_assessment(first.assessment.assessment_id) == first.assessment
        assert repository.get_receipt(request.command_id) == first.receipt
        assert repository._connection.total_changes == before
        assert counts(repository) == (1, 1)
    with SQLiteCapitalReadinessRepository(path) as repository:
        replay = owner(repository, fail=True)[0].execute(request)
        assert replay.replayed is True
        assert replay.assessment == first.assessment
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", (HISTORY, RECEIPTS))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_history_and_receipts_are_append_only(
    tmp_path: Path, table: str, operation: str
) -> None:
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    opportunity, conservative, critical, market = seed(path)
    request = persisted_request(type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })(), opportunity)
    with SQLiteCapitalReadinessRepository(path) as repository:
        owner(repository)[0].execute(request)
        statement = (
            f"UPDATE {table} SET command_fingerprint='x'"
            if operation == "UPDATE" and table == RECEIPTS
            else f"UPDATE {table} SET state='x'"
            if operation == "UPDATE"
            else f"DELETE FROM {table}"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(statement)
        repository._connection.rollback()
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize(
    ("table", "error"),
    ((HISTORY, CapitalReadinessHistoryError), (RECEIPTS, CapitalReadinessReceiptError)),
)
def test_insert_failures_roll_back(tmp_path: Path, table: str, error) -> None:
    path = tmp_path / f"rollback-{table}.sqlite3"
    opportunity, conservative, critical, market = seed(path)
    request = persisted_request(type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })(), opportunity)
    with SQLiteCapitalReadinessRepository(path) as repository:
        repository._connection.execute(
            f"CREATE TRIGGER forced BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'forced'); END"
        )
        with pytest.raises(error):
            owner(repository)[0].execute(request)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_commit_failure_rolls_back_and_retry_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "commit.sqlite3"
    opportunity, conservative, critical, market = seed(path)
    request = persisted_request(type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })(), opportunity)

    class Failing(SQLiteCapitalReadinessRepository):
        def _commit(self):
            raise sqlite3.OperationalError("forced")

    with Failing(path) as repository:
        with pytest.raises(CapitalReadinessCommitError):
            owner(repository)[0].execute(request)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
    with SQLiteCapitalReadinessRepository(path) as repository:
        assert owner(repository)[0].execute(request).replayed is False


def test_concurrent_same_and_changed_commands_converge(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.sqlite3"
    opportunity, conservative, critical, market = seed(path)
    sources = type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })()
    request = persisted_request(sources, opportunity)

    def run(value):
        with SQLiteCapitalReadinessRepository(path) as repository:
            return owner(repository, identity=f"assessment-{value}")[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run, ("one", "two")))
    assert len({result.assessment.assessment_id for result in results}) == 1
    with SQLiteCapitalReadinessRepository(path) as repository:
        assert counts(repository) == (1, 1)

    changed_path = tmp_path / "changed.sqlite3"
    opportunity, conservative, critical, market = seed(changed_path)
    sources = type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })()

    gate = Barrier(2)

    class ConcurrentRepository(SQLiteCapitalReadinessRepository):
        def save_assessment(self, command, assessment, receipt):
            gate.wait(timeout=10)
            return super().save_assessment(command, assessment, receipt)

    requests = (
        persisted_request(sources, opportunity),
        persisted_request(
            sources,
            opportunity,
            requested_at=NOW + timedelta(seconds=1),
        ),
    )

    def run_changed(index):
        try:
            with ConcurrentRepository(changed_path) as repository:
                return owner(repository, identity=f"changed-{index}")[0].execute(
                    requests[index]
                )
        except CapitalReadinessReplayConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(run_changed, (0, 1)))
    assert sum(not isinstance(value, Exception) for value in outcomes) == 1
    assert sum(isinstance(value, CapitalReadinessReplayConflictError) for value in outcomes) == 1
    with SQLiteCapitalReadinessRepository(changed_path) as repository:
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize(
    "case",
    (
        "invalid_state", "invalid_reason", "wrong_order", "unsupported_policy",
        "unsupported_schema", "missing_source_id", "opportunity_mismatch",
        "invalid_timestamp", "ready_with_blocker", "fingerprint",
    ),
)
def test_malformed_persistence_is_rejected(tmp_path: Path, case: str) -> None:
    path = tmp_path / f"malformed-{case}.sqlite3"
    opportunity, conservative, critical, market = seed(path)
    sources = type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })()
    request = persisted_request(sources, opportunity)
    with SQLiteCapitalReadinessRepository(path) as repository:
        publication = owner(repository)[0].execute(request)
    raw = sqlite3.connect(path)
    raw.execute("DROP TRIGGER trg_capital_readiness_history_no_update")
    encoded = raw.execute(
        f"SELECT payload_json FROM {HISTORY} WHERE assessment_id=?",
        (publication.assessment.assessment_id,),
    ).fetchone()[0]
    payload = json.loads(encoded)
    if case == "invalid_state":
        payload["state"] = "approved"
    elif case == "invalid_reason":
        payload["state"] = "blocked"
        payload["blocking_reasons"] = ["invented"]
    elif case == "wrong_order":
        payload["state"] = "blocked"
        payload["blocking_reasons"] = ["quote_expired", "conservative_economics_blocked"]
    elif case == "unsupported_policy":
        payload["policy_version"] = "3.0.0"
    elif case == "unsupported_schema":
        payload["schema_version"] = "future"
    elif case == "missing_source_id":
        payload["source_manifest"]["quote_id"] = ""
    elif case == "opportunity_mismatch":
        payload["source_manifest"]["opportunity_identity"]["opportunity_id"] = "other"
    elif case == "invalid_timestamp":
        payload["evaluated_at"] = "2026-08-09T00:00:00"
    elif case == "ready_with_blocker":
        payload["blocking_reasons"] = ["quote_expired"]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = (
        "0" * 64 if case == "fingerprint" else hashlib.sha256(encoded.encode()).hexdigest()
    )
    raw.execute(
        f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=? WHERE assessment_id=?",
        (encoded, fingerprint, publication.assessment.assessment_id),
    )
    raw.commit()
    raw.close()
    with SQLiteCapitalReadinessRepository(path) as repository:
        with pytest.raises(MalformedCapitalReadinessPersistenceError):
            repository.get_assessment(publication.assessment.assessment_id)


def test_orphan_receipt_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "orphan.sqlite3"
    repository = SQLiteCapitalReadinessRepository(path)
    repository.close()
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(f"""INSERT INTO {RECEIPTS}(
        command_id,assessment_id,command_fingerprint,committed_at,schema_version,inserted_at
    ) VALUES(?,?,?,?,?,?)""", (
        "orphan", "missing", "0" * 64, NOW.isoformat(),
        "capital-readiness-receipt-v1", NOW.isoformat(),
    ))
    raw.commit()
    raw.close()
    with SQLiteCapitalReadinessRepository(path) as repository:
        with pytest.raises(MalformedCapitalReadinessPersistenceError):
            repository.get_receipt("orphan")
