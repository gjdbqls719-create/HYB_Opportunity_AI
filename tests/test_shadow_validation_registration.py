from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.application.candidate_issuance import CandidateIssuanceProductionEntry
from app.application.candidate_promotion import (
    CandidatePromotionProductionEntry,
    PromoteOpportunityCandidateV2Command,
)
from app.application.discovery import (
    DiscoveryScreeningCompletionBinding,
    DiscoveryScreeningCompletionBundle,
)
from app.application.new_to_market_domestic_selling import (
    AdmitNewToMarketDomesticSellingOpportunity,
)
from app.application.shadow_validation_persistence import (
    ShadowRegistrationReplayConflictError,
)
from app.application.shadow_validation_registration import (
    RegisterShadowValidation,
    RegisterShadowValidationCommand,
    ShadowValidationHindsightError,
    ShadowValidationLegacyScreeningError,
    ShadowValidationLineageError,
)
from app.domain.discovery import (
    DiscoveryScreeningRankingPublication,
    DiscoveryScreeningRecordingState,
    RankedScreeningEntry,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.domain.opportunity import (
    ShadowBaselineSourceRole,
    ShadowCalibrationEligibility,
    ShadowEvidenceClass,
)
from app.infrastructure.discovery import (
    SQLiteCandidateIssuanceRepository,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
    SQLiteDiscoveryScreeningCompletionRepository,
)
from app.infrastructure.new_to_market_domestic_selling import (
    SQLiteNewToMarketDomesticSellingAdmissionRepository,
)
from app.infrastructure.opportunity_validation import (
    SQLiteCandidatePromotionRepository,
)
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from app.infrastructure.shadow_validation import (
    BASELINE_HISTORY_TABLE,
    REQUEST_RECEIPT_TABLE,
    SQLiteShadowRegistrationBaselineRepository,
)
from app.web import app, get_shadow_validation_registration_entry
from test_candidate_issuance_foundation import Counter, issuance_command
from test_candidate_promotion_v2 import _v2_payload
from test_discovery_execution_result_sqlite_persistence import prepare_group
from test_discovery_screening_domain_contracts import (
    NOW as SCREENING_NOW,
    evaluation,
)
from discovery_screening_persistence_support import prepare_bundle
from test_new_to_market_domestic_selling_foundation import _command, _search
from test_product_snapshot_capture_production_entry import (
    capture_request,
    production_entry,
)


EVALUATED_AT = SCREENING_NOW + timedelta(minutes=1)
RANKED_AT = SCREENING_NOW + timedelta(minutes=2)
COMPLETED_AT = SCREENING_NOW + timedelta(minutes=3)
CANDIDATE_AT = SCREENING_NOW + timedelta(minutes=4)
CAPTURED_AT = SCREENING_NOW + timedelta(minutes=5)
PROMOTED_AT = SCREENING_NOW + timedelta(minutes=6)
SEARCHED_AT = SCREENING_NOW + timedelta(minutes=7)
VERIFIED_AT = SCREENING_NOW + timedelta(minutes=8)
O2_REQUESTED_AT = SCREENING_NOW + timedelta(minutes=9)
O2_ADMITTED_AT = SCREENING_NOW + timedelta(minutes=10)
O2_COMMITTED_AT = SCREENING_NOW + timedelta(minutes=11)
REGISTER_REQUESTED_AT = SCREENING_NOW + timedelta(minutes=12)
REGISTERED_AT = SCREENING_NOW + timedelta(minutes=13)
SHADOW_COMMITTED_AT = SCREENING_NOW + timedelta(minutes=14)


class FailDependency:
    def __init__(self):
        self.calls = 0

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            self.calls += 1
            raise AssertionError(f"replay/get must not resolve {name}")

        return fail

    def __call__(self):
        self.calls += 1
        raise AssertionError("replay/get must not call identity or clock")


@dataclass
class PreparedShadowAuthorities:
    path: object
    o2: SQLiteNewToMarketDomesticSellingAdmissionRepository
    candidates: SQLiteCandidateIssuanceRepository
    promotions: SQLiteCandidatePromotionRepository
    screening: SQLiteDiscoveryScreeningCompletionRepository
    shadow: SQLiteShadowRegistrationBaselineRepository
    entry: RegisterShadowValidation
    id_clock_dependencies: tuple[Counter, Counter, Counter, Counter]
    resources: tuple[object, ...]

    def close(self):
        app.dependency_overrides.clear()
        for resource in reversed(self.resources):
            resource.close()


def _screening_bundle(path, *, future_input=False):
    prepare_group(path)
    group_repository = SQLiteDiscoveryGroupRepository(path)
    group = group_repository.get_group("group-opaque-1")
    group_repository.close()
    assert group is not None
    evaluation_value = evaluation(
        evaluation_id="screening-evaluation-shadow-1",
        group_id=group.finalized_group_id,
        evaluated_at=EVALUATED_AT,
    )
    evaluation_value = replace(
        evaluation_value,
        group_membership_fingerprint=group.membership_fingerprint,
        integrity_fingerprint="",
    )
    if future_input:
        inputs = tuple(
            replace(
                item,
                evidence=replace(
                    item.evidence,
                    source_references=tuple(
                        replace(reference, observed_at=EVALUATED_AT + timedelta(days=1))
                        for reference in item.evidence.source_references
                    ),
                ),
            )
            for item in evaluation_value.input_manifest.inputs
        )
        evaluation_value = replace(
            evaluation_value,
            input_manifest=replace(evaluation_value.input_manifest, inputs=inputs),
            integrity_fingerprint="",
        )
    ranking = DiscoveryScreeningRankingPublication(
        screening_ranking_publication_id="screening-publication-shadow-1",
        command_id="command-1",
        discovery_execution_id="execution-1",
        ranked_entries=(
            RankedScreeningEntry(
                rank=1,
                discovery_execution_id="execution-1",
                finalized_group_id=group.finalized_group_id,
                screening_evaluation_id=evaluation_value.screening_evaluation_id,
                evaluation_fingerprint=evaluation_value.integrity_fingerprint,
            ),
        ),
        not_ranked_entries=(),
        ranking_policy=evaluation_value.screening_policy_manifest.ranking,
        ranking_created_at=RANKED_AT,
        zero_result=False,
    )
    result = DiscoveryExecutionResult(
        command_id="command-1",
        discovery_execution_id="execution-1",
        finalized_group_ids=(group.finalized_group_id,),
        completed_at=COMPLETED_AT,
    )
    binding = DiscoveryScreeningCompletionBinding(
        command_id=result.command_id,
        discovery_execution_id=result.discovery_execution_id,
        result_schema_version=result.schema_version,
        result_fingerprint=result.fingerprint,
        screening_ranking_publication_id=ranking.screening_ranking_publication_id,
        ranking_publication_fingerprint=ranking.integrity_fingerprint,
    )
    return DiscoveryScreeningCompletionBundle(
        execution_result=result,
        finalized_groups=(group,),
        evaluations=(evaluation_value,),
        ranking_publication=ranking,
        completion_binding=binding,
    )


def _prepare(tmp_path, *, future_input=False) -> PreparedShadowAuthorities:
    path = tmp_path / "shadow-registration.db"
    screening = SQLiteDiscoveryScreeningCompletionRepository(path)
    screening.save_completion_bundle(
        _screening_bundle(path, future_input=future_input)
    )

    commands = SQLiteDiscoveryCommandRepository(path)
    results = SQLiteDiscoveryResultRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    candidates = SQLiteCandidateIssuanceRepository(path)
    issuance = CandidateIssuanceProductionEntry(
        command_repository=commands,
        result_repository=results,
        group_repository=groups,
        observation_repository=observations,
        candidate_repository=candidates,
        candidate_id_generator=Counter("candidate-1"),
        issuance_clock=Counter(CANDIDATE_AT),
        receipt_clock=Counter(CANDIDATE_AT),
    ).execute(issuance_command(requested_at=CANDIDATE_AT)).issuance

    captures = SQLiteProductSnapshotCaptureRepository(path)
    production_entry(
        candidates, groups, captures, Counter(CAPTURED_AT)
    ).execute(capture_request(issuance, requested_at=CAPTURED_AT))
    promotions = SQLiteCandidatePromotionRepository(path)
    promotion_entry = CandidatePromotionProductionEntry(
        candidate_repository=candidates,
        product_snapshot_capture_repository=captures,
        promotion_repository=promotions,
        opportunity_id_generator=Counter("opportunity-v2-1"),
        binding_id_generator=Counter("binding-v2-1"),
        admission_id_generator=Counter("admission-v2-1"),
        clock=Counter(PROMOTED_AT),
    )
    promotion_payload = _v2_payload(requested_at=PROMOTED_AT)
    promotion_entry.execute_v2(
        PromoteOpportunityCandidateV2Command(**promotion_payload)
    )

    o2 = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    o2_entry = AdmitNewToMarketDomesticSellingOpportunity(
        o2,
        opportunity_id_generator=Counter("new-market-o2-1"),
        target_id_generator=Counter("new-market-target-1"),
        admission_id_generator=Counter("new-market-admission-1"),
        admitted_clock=Counter(O2_ADMITTED_AT),
        committed_clock=Counter(O2_COMMITTED_AT),
    )
    o2_entry.execute(
        _command(
            search_manifest=_search(performed_at=SEARCHED_AT),
            verified_at=VERIFIED_AT,
            requested_at=O2_REQUESTED_AT,
        )
    )

    shadow = SQLiteShadowRegistrationBaselineRepository(path)
    dependencies = (
        Counter("shadow-validation-1"),
        Counter("shadow-baseline-1"),
        Counter(REGISTERED_AT),
        Counter(SHADOW_COMMITTED_AT),
    )
    entry = RegisterShadowValidation(
        o2_repository=o2,
        candidate_repository=candidates,
        promotion_repository=promotions,
        screening_repository=screening,
        shadow_repository=shadow,
        shadow_validation_id_generator=dependencies[0],
        baseline_snapshot_id_generator=dependencies[1],
        registered_clock=dependencies[2],
        committed_clock=dependencies[3],
    )
    return PreparedShadowAuthorities(
        path,
        o2,
        candidates,
        promotions,
        screening,
        shadow,
        entry,
        dependencies,
        (
            commands,
            results,
            groups,
            observations,
            candidates,
            captures,
            promotions,
            o2,
            screening,
            shadow,
        ),
    )


def _command_request(**changes) -> RegisterShadowValidationCommand:
    values = {
        "command_id": "register-shadow-command-1",
        "o2_admission_id": "new-market-admission-1",
        "domestic_selling_target_id": "new-market-target-1",
        "screening_ranking_publication_id": "screening-publication-shadow-1",
        "screening_evaluation_id": "screening-evaluation-shadow-1",
        "operator_id": "founder",
        "registration_reason": "preserve the exact unfunded machine thesis",
        "requested_at": REGISTER_REQUESTED_AT,
    }
    values.update(changes)
    return RegisterShadowValidationCommand(**values)


def _api_payload(**changes):
    values = {
        "command_id": "register-shadow-command-1",
        "o2_admission_id": "new-market-admission-1",
        "domestic_selling_target_id": "new-market-target-1",
        "screening_ranking_publication_id": "screening-publication-shadow-1",
        "screening_evaluation_id": "screening-evaluation-shadow-1",
        "operator_id": "founder",
        "registration_reason": "preserve the exact unfunded machine thesis",
        "requested_at": REGISTER_REQUESTED_AT.isoformat(),
    }
    values.update(changes)
    return values


def _non_shadow_state(connection):
    names = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'shadow_%' "
            "ORDER BY name"
        )
    )
    return tuple(
        (name, tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {name}")))
        for name in names
    )


def test_openapi_accepts_only_founder_references_and_intent():
    document = TestClient(app).get("/openapi.json").json()
    paths = document["paths"]
    assert set(paths["/api/v1/shadow-validations"]) == {"post"}
    assert set(paths["/api/v1/shadow-validations/{shadow_validation_id}"]) == {
        "get"
    }
    properties = document["components"]["schemas"][
        "ShadowValidationRegistrationRequest"
    ]["properties"]
    assert {
        "command_id",
        "o2_admission_id",
        "domestic_selling_target_id",
        "screening_ranking_publication_id",
        "screening_evaluation_id",
        "operator_id",
        "registration_reason",
        "requested_at",
        "cadence_policy_name",
        "cadence_policy_version",
    } == set(properties)
    assert {
        "shadow_validation_id",
        "baseline_snapshot_id",
        "screening_score",
        "recommendation",
        "source_fingerprint",
        "candidate_id",
        "o1_opportunity_id",
        "calibration_eligibility",
        "registered_at",
    }.isdisjoint(properties)


def test_application_registers_exact_o2_screening_baseline_without_side_effects(
    tmp_path,
):
    prepared = _prepare(tmp_path)
    try:
        before = _non_shadow_state(prepared.shadow._connection)
        result = prepared.entry.execute(_command_request())
        registration = result.registration
        baseline = result.baseline

        assert not result.replayed
        assert registration.shadow_validation_id == "shadow-validation-1"
        assert baseline.baseline_snapshot_id == "shadow-baseline-1"
        assert registration.subject.o2_opportunity_identity.opportunity_id == (
            "new-market-o2-1"
        )
        assert registration.subject.candidate_id == "candidate-1"
        assert registration.subject.o1_opportunity_identity.opportunity_id == (
            "opportunity-v2-1"
        )
        assert registration.screening_lineage.screening_evaluation_id == (
            "screening-evaluation-shadow-1"
        )
        assert registration.knowledge_cutoff_at == O2_COMMITTED_AT
        assert registration.registered_at == REGISTERED_AT
        assert registration.evidence_class is ShadowEvidenceClass.SHADOW_MARKET_THESIS
        assert baseline.evidence_class is ShadowEvidenceClass.SHADOW_MARKET_THESIS
        assert baseline.calibration_eligibility is ShadowCalibrationEligibility.ELIGIBLE
        assert baseline.calibration_reason_codes == ()
        assert tuple(
            source.baseline_role for source in baseline.source_manifest.sources
        ) == (
            ShadowBaselineSourceRole.O2_SUBJECT_LINEAGE,
            ShadowBaselineSourceRole.SCREENING_EVALUATION,
            ShadowBaselineSourceRole.SCREENING_RANKING_PUBLICATION,
            ShadowBaselineSourceRole.SCREENING_USED_INPUT_MANIFEST,
        )
        o2_source = baseline.source_manifest.sources[0]
        assert o2_source.generated_at == O2_ADMITTED_AT
        assert o2_source.committed_at == O2_COMMITTED_AT
        assert baseline.source_manifest.sources[-1].generated_at == EVALUATED_AT
        assert prepared.shadow._connection.execute(
            f"SELECT COUNT(*) FROM {REQUEST_RECEIPT_TABLE}"
        ).fetchone()[0] == 1
        assert _non_shadow_state(prepared.shadow._connection) == before
        assert not any(
            "checkpoint" in row[0]
            for row in prepared.shadow._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        )
    finally:
        prepared.close()


def test_request_replay_is_receipt_first_and_changed_request_conflicts(tmp_path):
    prepared = _prepare(tmp_path)
    try:
        first = prepared.entry.execute(_command_request())
        fail = FailDependency()
        replay_entry = RegisterShadowValidation(
            o2_repository=fail,
            candidate_repository=fail,
            promotion_repository=fail,
            screening_repository=fail,
            shadow_repository=prepared.shadow,
            shadow_validation_id_generator=fail,
            baseline_snapshot_id_generator=fail,
            registered_clock=fail,
            committed_clock=fail,
        )
        replay = replay_entry.execute(_command_request())
        assert replay.replayed
        assert replay.registration == first.registration
        assert replay.baseline == first.baseline
        assert fail.calls == 0

        with pytest.raises(
            ShadowRegistrationReplayConflictError, match="request payload conflicts"
        ):
            replay_entry.execute(_command_request(registration_reason="changed"))
        assert fail.calls == 0
        assert tuple(
            prepared.shadow._connection.execute(
                "SELECT (SELECT COUNT(*) FROM shadow_validation_registration_history), "
                "(SELECT COUNT(*) FROM shadow_baseline_snapshot_history), "
                "(SELECT COUNT(*) FROM shadow_registration_receipts), "
                "(SELECT COUNT(*) FROM shadow_registration_request_receipts)"
            ).fetchone()
        ) == (1, 1, 1, 1)
    finally:
        prepared.close()


def test_lineage_legacy_and_hindsight_fail_closed(tmp_path):
    prepared = _prepare(tmp_path)
    try:
        with pytest.raises(ShadowValidationLineageError, match="differ"):
            prepared.entry.execute(
                _command_request(domestic_selling_target_id="other-target")
            )

        class LegacyScreening:
            def get_recording_state(self, execution_id):
                return DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY

        legacy_entry = RegisterShadowValidation(
            o2_repository=prepared.o2,
            candidate_repository=prepared.candidates,
            promotion_repository=prepared.promotions,
            screening_repository=LegacyScreening(),
            shadow_repository=prepared.shadow,
            shadow_validation_id_generator=Counter("unused-shadow"),
            baseline_snapshot_id_generator=Counter("unused-baseline"),
            registered_clock=Counter(REGISTERED_AT),
            committed_clock=Counter(SHADOW_COMMITTED_AT),
        )
        with pytest.raises(ShadowValidationLegacyScreeningError):
            legacy_entry.execute(_command_request(command_id="legacy-command"))

        actual_publication = prepared.o2.get_admission("new-market-admission-1")
        assert actual_publication is not None

        class ConflictingO2:
            def __init__(self, changed_publication):
                self.changed_publication = changed_publication

            def get_admission(self, admission_id):
                return self.changed_publication

            def get_target_binding(self, opportunity_id):
                return prepared.o2.get_target_binding(opportunity_id)

            def get_promotion_v2_admission(self, opportunity_id):
                return prepared.o2.get_promotion_v2_admission(opportunity_id)

        for changes in (
            {"candidate_id": "other-candidate"},
            {"candidate_opportunity_binding_id": "other-o1-binding"},
        ):
            changed_source = replace(
                actual_publication.admission.source_manifest, **changes
            )
            changed_publication = replace(
                actual_publication,
                admission=replace(
                    actual_publication.admission, source_manifest=changed_source
                ),
            )
            conflicting_entry = RegisterShadowValidation(
                o2_repository=ConflictingO2(changed_publication),
                candidate_repository=prepared.candidates,
                promotion_repository=prepared.promotions,
                screening_repository=prepared.screening,
                shadow_repository=prepared.shadow,
                shadow_validation_id_generator=Counter("unused-shadow"),
                baseline_snapshot_id_generator=Counter("unused-baseline"),
                registered_clock=Counter(REGISTERED_AT),
                committed_clock=Counter(SHADOW_COMMITTED_AT),
            )
            with pytest.raises(ShadowValidationLineageError, match="differ"):
                conflicting_entry.execute(
                    _command_request(command_id=f"conflict-{next(iter(changes))}")
                )
    finally:
        prepared.close()

    prepared = _prepare(tmp_path / "future", future_input=True)
    try:
        with pytest.raises(ShadowValidationHindsightError, match="follows"):
            prepared.entry.execute(_command_request())
        assert prepared.shadow.get_bundle("shadow-validation-1") is None
    finally:
        prepared.close()


def test_screening_publication_membership_and_execution_mismatch_fail_closed(tmp_path):
    prepared = _prepare(tmp_path)
    try:
        selected = prepared.screening.get_evaluation(
            "screening-evaluation-shadow-1"
        )
        assert selected is not None
        outside = replace(
            selected,
            screening_evaluation_id="outside-evaluation",
            integrity_fingerprint="",
        )

        class OutsideEvaluationScreening:
            def get_recording_state(self, execution_id):
                return prepared.screening.get_recording_state(execution_id)

            def get_by_publication(self, publication_id):
                return prepared.screening.get_by_publication(publication_id)

            def get_ranking_publication(self, publication_id):
                return prepared.screening.get_ranking_publication(publication_id)

            def get_evaluation(self, evaluation_id):
                return outside

        outside_entry = RegisterShadowValidation(
            o2_repository=prepared.o2,
            candidate_repository=prepared.candidates,
            promotion_repository=prepared.promotions,
            screening_repository=OutsideEvaluationScreening(),
            shadow_repository=prepared.shadow,
            shadow_validation_id_generator=Counter("unused-shadow"),
            baseline_snapshot_id_generator=Counter("unused-baseline"),
            registered_clock=Counter(REGISTERED_AT),
            committed_clock=Counter(SHADOW_COMMITTED_AT),
        )
        with pytest.raises(ShadowValidationLineageError, match="does not belong"):
            outside_entry.execute(
                _command_request(
                    command_id="outside-evaluation-command",
                    screening_evaluation_id="outside-evaluation",
                )
            )

        other = prepare_bundle(
            prepared.path,
            command_id="other-command",
            execution_id="other-execution",
            suffix="2",
            group_count=1,
        )
        prepared.screening.save_completion_bundle(other)
        with pytest.raises(ShadowValidationLineageError, match="differ"):
            prepared.entry.execute(
                _command_request(
                    command_id="other-screening-command",
                    screening_ranking_publication_id="publication-2",
                    screening_evaluation_id="evaluation-2-1",
                )
            )
    finally:
        prepared.close()


def test_http_post_get_exact_authority_and_no_commerce_fields(tmp_path):
    prepared = _prepare(tmp_path)
    app.dependency_overrides[get_shadow_validation_registration_entry] = (
        lambda: prepared.entry
    )
    client = TestClient(app)
    try:
        created = client.post("/api/v1/shadow-validations", json=_api_payload())
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["shadow_validation_id"] == "shadow-validation-1"
        assert body["baseline_snapshot_id"] == "shadow-baseline-1"
        assert body["authority_kind"] == "MACHINE_SCREENING_BASED"
        assert body["authority_scope"] == "ELAPSED_TIME_MARKET_THESIS_VALIDATION"
        assert body["evidence_class"] == "SHADOW_MARKET_THESIS"
        assert body["calibration_eligibility"] == "ELIGIBLE"
        assert body["authority_statement"] == (
            "This Opportunity has entered elapsed-time market-thesis validation."
        )
        assert {
            "INVESTMENT_APPROVAL",
            "BUY_AUTHORIZATION",
            "CAPITAL_READINESS",
            "PRODUCT_LAUNCH",
            "REVENUE",
            "PROFIT",
            "ACTUAL_OUTCOME",
        } == set(body["excluded_authorities"])
        assert not {
            "virtual_revenue",
            "virtual_profit",
            "expected_units_sold",
            "actual_outcome",
        } & set(body)

        replay = client.post("/api/v1/shadow-validations", json=_api_payload())
        assert replay.status_code == 200
        assert replay.json() == {**body, "replayed": True}
        detail = client.get("/api/v1/shadow-validations/shadow-validation-1")
        assert detail.status_code == 200
        assert detail.json() == {key: value for key, value in body.items() if key != "replayed"}
        assert client.get("/api/v1/shadow-validations/missing").status_code == 404
        assert client.post(
            "/api/v1/shadow-validations",
            json=_api_payload(registration_reason="changed"),
        ).status_code == 409
        assert client.post(
            "/api/v1/shadow-validations",
            json=_api_payload(command_id="missing-command", o2_admission_id="missing"),
        ).status_code == 404

        prepared.shadow._connection.execute(
            f"DROP TRIGGER trg_{BASELINE_HISTORY_TABLE}_no_update"
        )
        prepared.shadow._connection.execute(
            f"UPDATE {BASELINE_HISTORY_TABLE} SET payload_json='{{}}'"
        )
        prepared.shadow._connection.commit()
        assert client.get("/api/v1/shadow-validations/shadow-validation-1").status_code == 503
    finally:
        prepared.close()


def test_http_corrupt_screening_fails_closed(tmp_path):
    prepared = _prepare(tmp_path)
    app.dependency_overrides[get_shadow_validation_registration_entry] = (
        lambda: prepared.entry
    )
    try:
        prepared.screening._connection.execute(
            "DROP TRIGGER trg_discovery_screening_evaluation_history_no_update"
        )
        prepared.screening._connection.execute(
            "UPDATE discovery_screening_evaluation_history "
            "SET canonical_payload_json='{}'"
        )
        prepared.screening._connection.commit()
        response = TestClient(app).post(
            "/api/v1/shadow-validations", json=_api_payload()
        )
        assert response.status_code == 503
        assert prepared.shadow.get_bundle("shadow-validation-1") is None
    finally:
        prepared.close()


def test_get_is_persistence_only_and_request_receipt_is_atomic(tmp_path, monkeypatch):
    prepared = _prepare(tmp_path)
    try:
        original_fault = prepared.shadow._fault_point

        def fail(point):
            if point == "after_request_receipt":
                raise RuntimeError("request receipt fault")

        monkeypatch.setattr(prepared.shadow, "_fault_point", fail)
        with pytest.raises(RuntimeError, match="request receipt fault"):
            prepared.entry.execute(_command_request())
        assert tuple(
            prepared.shadow._connection.execute(
                "SELECT (SELECT COUNT(*) FROM shadow_validation_registration_history), "
                "(SELECT COUNT(*) FROM shadow_baseline_snapshot_history), "
                "(SELECT COUNT(*) FROM shadow_registration_receipts), "
                "(SELECT COUNT(*) FROM shadow_registration_request_receipts)"
            ).fetchone()
        ) == (0, 0, 0, 0)
        monkeypatch.setattr(prepared.shadow, "_fault_point", original_fault)
        prepared.entry.execute(_command_request())
        for operation in ("UPDATE", "DELETE"):
            statement = (
                f"UPDATE {REQUEST_RECEIPT_TABLE} SET inserted_at=inserted_at"
                if operation == "UPDATE"
                else f"DELETE FROM {REQUEST_RECEIPT_TABLE}"
            )
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                prepared.shadow._connection.execute(statement)
            prepared.shadow._connection.rollback()

        fail_source = FailDependency()
        read_entry = RegisterShadowValidation(
            o2_repository=fail_source,
            candidate_repository=fail_source,
            promotion_repository=fail_source,
            screening_repository=fail_source,
            shadow_repository=prepared.shadow,
            shadow_validation_id_generator=fail_source,
            baseline_snapshot_id_generator=fail_source,
            registered_clock=fail_source,
            committed_clock=fail_source,
        )
        assert read_entry.get("shadow-validation-1").baseline.baseline_snapshot_id == (
            "shadow-baseline-1"
        )
        assert fail_source.calls == 0
    finally:
        prepared.close()
