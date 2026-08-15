from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal

import pytest

import app.application.capital_readiness as application_contract
import app.domain.capital as domain_contract
from app.application.capital_readiness import (
    CapitalReadinessProductionEntry,
    CapitalReadinessProductionRequestV2,
    CapitalReadinessReplayConflictError,
    EvaluateCapitalReadiness,
    EvaluateCapitalReadinessCommandV2,
)
from app.domain.capital import (
    CapitalReadinessReasonCode,
    CapitalReadinessState,
    CapitalGateState,
    DeployableCapitalSnapshot,
    DomesticMarketValidationSourceKind,
    DomesticMarketValidationSourceReference,
    IntendedOrderQuantity,
)
from app.domain.sourcing import (
    NEW_TO_MARKET_DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
    NewToMarketDomesticSellingProductLineage,
    SOURCING_AUTHORITY_SCHEMA_VERSION,
)
from test_capital_readiness import Calls, ready_sources
from test_capital_gate import (
    MemoryCapitalGateRepository,
    command as gate_command,
    owner as gate_owner,
    requirement,
)
from test_domestic_market_validation_v2 import (
    _command as dmv_v2_command,
    _complete_service,
)
from test_sourcing_authority_contract import NOW, command as sourcing_command


class TargetReadyRepository:
    def __init__(self, base, market_v2):
        self.base = base
        self.market_v2 = market_v2
        self.market_v2_reads = 0

    def __getattr__(self, name):
        return getattr(self.base, name)

    def get_domestic_market_validation_v2(self, assessment_id):
        self.market_v2_reads += 1
        return (
            self.market_v2
            if self.market_v2.assessment_id == assessment_id
            else None
        )


def _target_ready_sources(*, target_id=None, current_use=True):
    repository, opportunity = ready_sources()
    service = _complete_service()
    market = service.execute(
        dmv_v2_command(service, current=current_use)
    )
    binding = replace(
        market.source_manifest.target_binding,
        opportunity_id=opportunity.opportunity_id,
        discovery_reference=opportunity.discovery_reference,
    )
    if target_id is not None:
        binding = replace(
            binding,
            target_identity=replace(
                binding.target_identity,
                domestic_selling_target_id=target_id,
            ),
        )
    source_manifest = replace(market.source_manifest, target_binding=binding)
    verification = replace(
        market.verification,
        reviewed_source_manifest_fingerprint=source_manifest.fingerprint,
    )
    market = replace(
        market,
        source_manifest=source_manifest,
        verification=verification,
    )
    lineage = NewToMarketDomesticSellingProductLineage(
        opportunity,
        "new-market-admission-1",
        binding.target_identity,
    )
    repository.admission = replace(
        repository.admission,
        selling_product_lineage=lineage,
        match_verification=replace(
            repository.admission.match_verification,
            selling_product_lineage=lineage,
        ),
        schema_version=(
            NEW_TO_MARKET_DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION
        ),
    )
    return TargetReadyRepository(repository, market), opportunity


def _target_command(repository, opportunity, **changes):
    values = dict(
        command_id="capital-readiness-command-v2-1",
        opportunity_id=opportunity.opportunity_id,
        conservative_economics_result_id=repository.conservative.result_id,
        domestic_market_validation_source=DomesticMarketValidationSourceReference(
            DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V2,
            repository.market_v2.assessment_id,
        ),
        critical_cost_assessment_id="critical-assessment-1",
        requested_at=NOW,
    )
    values.update(changes)
    return EvaluateCapitalReadinessCommandV2(**values)


def _owner(repository):
    return EvaluateCapitalReadiness(
        repository,
        assessment_id_generator=Calls("capital-readiness-v3-1"),
        evaluated_clock=Calls(NOW),
        committed_clock=Calls(NOW),
    )


def _unchecked(value, **changes):
    result = object.__new__(type(value))
    for name in value.__dataclass_fields__:
        object.__setattr__(result, name, changes.get(name, getattr(value, name)))
    return result


def test_command_v2_uses_an_explicit_exact_dmv_source_reference() -> None:
    source_kind = getattr(
        domain_contract,
        "DomesticMarketValidationSourceKind",
        None,
    )
    source_reference_type = getattr(
        domain_contract,
        "DomesticMarketValidationSourceReference",
        None,
    )
    command_type = getattr(
        application_contract,
        "EvaluateCapitalReadinessCommandV2",
        None,
    )

    assert source_kind is not None, "ADR-0066 source kind contract is missing"
    assert source_reference_type is not None, "ADR-0066 source reference is missing"
    assert command_type is not None, "ADR-0066 command-v2 contract is missing"

    reference = source_reference_type(
        source_kind.DOMESTIC_MARKET_VALIDATION_V2,
        "dmv-v2-assessment-1",
    )
    command = command_type(
        command_id="capital-readiness-command-v2-1",
        opportunity_id="new-market-o2-1",
        conservative_economics_result_id="conservative-result-1",
        domestic_market_validation_source=reference,
        critical_cost_assessment_id="critical-assessment-1",
        requested_at=NOW,
    )

    assert {field.name for field in fields(command)} == {
        "command_id",
        "opportunity_id",
        "conservative_economics_result_id",
        "domestic_market_validation_source",
        "critical_cost_assessment_id",
        "requested_at",
        "policy_name",
        "policy_version",
        "schema_version",
    }
    assert not hasattr(command, "opportunity_identity")
    assert not hasattr(reference, "source_manifest_fingerprint")
    assert not hasattr(reference, "target_identity")
    assert tuple(CapitalReadinessState) == (
        CapitalReadinessState.READY_FOR_CAPITAL_REVIEW,
        CapitalReadinessState.BLOCKED,
    )
    assert tuple(CapitalReadinessReasonCode) == (
        CapitalReadinessReasonCode.CONSERVATIVE_ECONOMICS_BLOCKED,
        CapitalReadinessReasonCode.DOMESTIC_MARKET_NOT_VALIDATED,
        CapitalReadinessReasonCode.CRITICAL_COST_INCOMPLETE,
        CapitalReadinessReasonCode.SOURCE_OPPORTUNITY_MISMATCH,
        CapitalReadinessReasonCode.SOURCING_LINEAGE_MISMATCH,
        CapitalReadinessReasonCode.PRODUCT_MATCH_NOT_VERIFIED,
        CapitalReadinessReasonCode.QUOTE_VALIDITY_MISSING,
        CapitalReadinessReasonCode.QUOTE_EXPIRED,
        CapitalReadinessReasonCode.SOURCE_POLICY_UNSUPPORTED,
    )


@pytest.mark.parametrize(
    ("kind", "assessment_id"),
    (("future_dmv", "assessment-1"), ("domestic_market_validation_v2", " ")),
)
def test_source_reference_rejects_unknown_kind_or_empty_exact_id(
    kind,
    assessment_id,
) -> None:
    with pytest.raises(ValueError):
        DomesticMarketValidationSourceReference(kind, assessment_id)


@pytest.mark.parametrize(
    "caller_field",
    (
        "target_identity",
        "market_observation_identity",
        "source_manifest_fingerprint",
        "discovery_reference",
    ),
)
def test_command_v2_rejects_caller_owned_subject_or_manifest_fields(
    caller_field,
) -> None:
    values = dict(
        command_id="capital-readiness-command-v2-forbidden",
        opportunity_id="new-market-o2-1",
        conservative_economics_result_id="conservative-result-1",
        domestic_market_validation_source=DomesticMarketValidationSourceReference(
            DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V2,
            "dmv-v2-assessment-1",
        ),
        critical_cost_assessment_id="critical-assessment-1",
        requested_at=NOW,
    )
    values[caller_field] = "caller-owned"

    with pytest.raises(TypeError):
        EvaluateCapitalReadinessCommandV2(**values)


def test_command_v2_fingerprint_pins_kind_and_exact_assessment_id() -> None:
    source_kind = getattr(domain_contract, "DomesticMarketValidationSourceKind")
    source_reference_type = getattr(
        domain_contract,
        "DomesticMarketValidationSourceReference",
    )
    command_type = getattr(
        application_contract,
        "EvaluateCapitalReadinessCommandV2",
    )
    command = command_type(
        command_id="capital-readiness-command-v2-1",
        opportunity_id="new-market-o2-1",
        conservative_economics_result_id="conservative-result-1",
        domestic_market_validation_source=source_reference_type(
            source_kind.DOMESTIC_MARKET_VALIDATION_V2,
            "dmv-v2-assessment-1",
        ),
        critical_cost_assessment_id="critical-assessment-1",
        requested_at=NOW,
    )

    assert command.fingerprint != replace(
        command,
        domestic_market_validation_source=source_reference_type(
            source_kind.DOMESTIC_MARKET_VALIDATION_V1,
            "dmv-v2-assessment-1",
        ),
    ).fingerprint
    assert command.fingerprint != replace(
        command,
        domestic_market_validation_source=source_reference_type(
            source_kind.DOMESTIC_MARKET_VALIDATION_V2,
            "dmv-v2-assessment-2",
        ),
    ).fingerprint


def test_exact_target_bound_dmv_v2_and_sourcing_target_are_ready() -> None:
    repository, opportunity = _target_ready_sources()

    publication = _owner(repository).execute(
        _target_command(repository, opportunity)
    )

    assessment = publication.assessment
    manifest = assessment.source_manifest
    assert assessment.state is CapitalReadinessState.READY_FOR_CAPITAL_REVIEW
    assert assessment.blocking_reasons == ()
    assert assessment.schema_version == "capital-readiness-v3"
    assert manifest.schema_version == "capital-readiness-source-manifest-v2"
    assert manifest.domestic_market_validation_source_kind is (
        DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V2
    )
    assert manifest.domestic_market_validation_assessment_id == (
        repository.market_v2.assessment_id
    )
    assert manifest.domestic_market_validation_source_manifest_fingerprint == (
        repository.market_v2.source_manifest_fingerprint
    )
    assert manifest.critical_cost_normalization_id == (
        repository.critical.acquisition_normalization_id
    )
    assert not hasattr(manifest, "target_identity")


@pytest.mark.parametrize(
    "change",
    (
        {"domestic_market_validation_source_kind": None},
        {"domestic_market_validation_source_kind": "future_dmv"},
        {
            "domestic_market_validation_source_manifest_fingerprint": (
                "not-a-sha256"
            )
        },
        {"critical_cost_normalization_id": None},
    ),
)
def test_source_manifest_v2_rejects_missing_or_malformed_authority_pins(
    change,
) -> None:
    repository, opportunity = _target_ready_sources()
    assessment = _owner(repository).execute(
        _target_command(repository, opportunity)
    ).assessment

    with pytest.raises((TypeError, ValueError)):
        replace(assessment.source_manifest, **change)


def test_assessment_v3_requires_source_manifest_v2() -> None:
    target_repository, opportunity = _target_ready_sources()
    target = _owner(target_repository).execute(
        _target_command(target_repository, opportunity)
    ).assessment
    legacy_repository, legacy_opportunity = ready_sources()
    legacy = _owner(legacy_repository).execute(
        EvaluateCapitalReadinessCommandV2(
            "command-v2-explicit-v1-for-version-test",
            legacy_opportunity.opportunity_id,
            legacy_repository.conservative.result_id,
            DomesticMarketValidationSourceReference(
                DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V1,
                legacy_repository.market.assessment_id,
            ),
            "critical-assessment-1",
            NOW,
        )
    ).assessment
    historical_manifest = replace(
        legacy.source_manifest,
        schema_version="capital-readiness-source-manifest-v1",
        domestic_market_validation_source_kind=None,
        critical_cost_normalization_id=None,
    )

    with pytest.raises(ValueError, match="versions differ"):
        replace(target, source_manifest=historical_manifest)


def test_command_v2_can_explicitly_pin_v1_without_changing_v1_authority() -> None:
    repository, opportunity = ready_sources()
    command = EvaluateCapitalReadinessCommandV2(
        command_id="capital-readiness-command-explicit-v1",
        opportunity_id=opportunity.opportunity_id,
        conservative_economics_result_id=repository.conservative.result_id,
        domestic_market_validation_source=DomesticMarketValidationSourceReference(
            DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V1,
            repository.market.assessment_id,
        ),
        critical_cost_assessment_id="critical-assessment-1",
        requested_at=NOW,
    )

    assessment = _owner(repository).execute(command).assessment

    assert assessment.state is CapitalReadinessState.READY_FOR_CAPITAL_REVIEW
    assert assessment.schema_version == "capital-readiness-v3"
    assert assessment.source_manifest.domestic_market_validation_source_kind is (
        DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V1
    )
    assert (
        assessment.source_manifest.domestic_market_validation_source_manifest_fingerprint
        is None
    )
    with pytest.raises(ValueError, match="DMV v1 source"):
        replace(
            assessment.source_manifest,
            domestic_market_validation_source_manifest_fingerprint="f" * 64,
        )


def test_blocked_dmv_v2_and_route_mismatch_use_existing_readiness_reasons() -> None:
    repository, opportunity = _target_ready_sources(current_use=False)
    command = _target_command(
        repository,
        opportunity,
        opportunity_id="different-route-opportunity",
    )

    assessment = _owner(repository).execute(command).assessment

    assert tuple(reason.code for reason in assessment.blocking_reasons) == (
        CapitalReadinessReasonCode.DOMESTIC_MARKET_NOT_VALIDATED,
        CapitalReadinessReasonCode.SOURCE_OPPORTUNITY_MISMATCH,
    )


def test_dmv_v2_internal_opportunity_lineage_mismatch_uses_existing_reason() -> None:
    repository, opportunity = _target_ready_sources()
    source_manifest = replace(
        repository.market_v2.source_manifest,
        target_binding=replace(
            repository.market_v2.source_manifest.target_binding,
            discovery_reference="different-discovery-reference",
        ),
    )
    repository.market_v2 = replace(
        repository.market_v2,
        source_manifest=source_manifest,
        verification=replace(
            repository.market_v2.verification,
            reviewed_source_manifest_fingerprint=source_manifest.fingerprint,
        ),
    )

    assessment = _owner(repository).execute(
        _target_command(repository, opportunity)
    ).assessment

    assert tuple(reason.code for reason in assessment.blocking_reasons) == (
        CapitalReadinessReasonCode.SOURCE_OPPORTUNITY_MISMATCH,
    )


def test_unsupported_dmv_v2_policy_uses_existing_policy_reason() -> None:
    repository, opportunity = _target_ready_sources()
    repository.market_v2 = _unchecked(
        repository.market_v2,
        policy_version="future-policy",
    )

    assessment = _owner(repository).execute(
        _target_command(repository, opportunity)
    ).assessment

    assert tuple(reason.code for reason in assessment.blocking_reasons) == (
        CapitalReadinessReasonCode.SOURCE_POLICY_UNSUPPORTED,
    )


def test_target_mismatch_uses_existing_sourcing_lineage_reason() -> None:
    repository, opportunity = _target_ready_sources()
    repository.base.admission = replace(
        repository.admission,
        selling_product_lineage=replace(
            repository.admission.selling_product_lineage,
            target_identity=replace(
                repository.admission.selling_product_lineage.target_identity,
                domestic_selling_target_id="different-target",
            ),
        ),
        match_verification=replace(
            repository.admission.match_verification,
            selling_product_lineage=replace(
                repository.admission.selling_product_lineage,
                target_identity=replace(
                    repository.admission.selling_product_lineage.target_identity,
                    domestic_selling_target_id="different-target",
                ),
            ),
        ),
    )

    assessment = _owner(repository).execute(
        _target_command(repository, opportunity)
    ).assessment

    assert assessment.state is CapitalReadinessState.BLOCKED
    assert tuple(reason.code for reason in assessment.blocking_reasons) == (
        CapitalReadinessReasonCode.SOURCING_LINEAGE_MISMATCH,
    )


def test_dmv_v2_requires_the_target_aware_sourcing_lineage_kind() -> None:
    repository, opportunity = _target_ready_sources()
    legacy_lineage = replace(
        sourcing_command().selling_product_lineage,
        opportunity_identity=opportunity,
    )
    repository.base.admission = replace(
        repository.admission,
        selling_product_lineage=legacy_lineage,
        match_verification=replace(
            repository.admission.match_verification,
            selling_product_lineage=legacy_lineage,
        ),
        schema_version=SOURCING_AUTHORITY_SCHEMA_VERSION,
    )

    assessment = _owner(repository).execute(
        _target_command(repository, opportunity)
    ).assessment

    assert assessment.state is CapitalReadinessState.BLOCKED
    assert tuple(reason.code for reason in assessment.blocking_reasons) == (
        CapitalReadinessReasonCode.SOURCING_LINEAGE_MISMATCH,
    )


def test_command_v2_replay_is_source_free_and_changed_reference_conflicts() -> None:
    repository, opportunity = _target_ready_sources()
    command = _target_command(repository, opportunity)
    entry = CapitalReadinessProductionEntry(repository, _owner(repository))
    request = CapitalReadinessProductionRequestV2(
        command.command_id,
        command.opportunity_id,
        command.conservative_economics_result_id,
        command.domestic_market_validation_source,
        command.critical_cost_assessment_id,
        command.requested_at,
    )
    first = entry.execute(request)
    repository.base.source_reads = 0
    repository.market_v2_reads = 0

    replay = entry.execute(request)

    assert replay.publication.replayed is True
    assert replay.publication.assessment == first.publication.assessment
    assert repository.base.source_reads == 0
    assert repository.market_v2_reads == 0

    changed_requests = (
        replace(
            request,
            domestic_market_validation_source=(
                DomesticMarketValidationSourceReference(
                    DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V1,
                    request.domestic_market_validation_source.assessment_id,
                )
            ),
        ),
        replace(
            request,
            domestic_market_validation_source=(
                DomesticMarketValidationSourceReference(
                    DomesticMarketValidationSourceKind.DOMESTIC_MARKET_VALIDATION_V2,
                    "different-exact-assessment",
                )
            ),
        ),
        replace(
            request,
            conservative_economics_result_id="different-conservative-result",
        ),
        replace(request, critical_cost_assessment_id="different-critical-cost"),
        replace(request, requested_at=NOW + timedelta(seconds=1)),
    )
    for changed in changed_requests:
        with pytest.raises(CapitalReadinessReplayConflictError):
            entry.execute(changed)
    assert repository.base.source_reads == 0
    assert repository.market_v2_reads == 0


def test_unchanged_capital_gate_consumes_target_backed_readiness() -> None:
    sources, opportunity = _target_ready_sources()
    readiness = _owner(sources).execute(
        _target_command(sources, opportunity)
    ).assessment
    admission = sources.admission
    intent = IntendedOrderQuantity(
        "intent-target-1",
        opportunity,
        admission.admission_id,
        admission.revision,
        admission.quote_revision.quote_id,
        admission.quote_revision.revision,
        25,
        "units",
        "founder-1",
        NOW,
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=2),
    )
    capital_requirement = requirement(
        intent,
        sources.normalization,
        admission,
    )
    deployable = DeployableCapitalSnapshot(
        "deployable-target-1",
        Decimal("1000"),
        capital_requirement.currency,
        NOW,
        "founder-1",
        NOW,
        NOW + timedelta(minutes=1),
    )
    repository = MemoryCapitalGateRepository(
        readiness,
        capital_requirement,
        deployable,
        sources.conservative,
        intent,
        admission,
    )

    gate = gate_owner(repository)[0].execute(
        gate_command(repository, opportunity)
    ).assessment

    assert gate.state is CapitalGateState.PASS
    assert gate.source_manifest.capital_readiness_assessment_id == (
        readiness.assessment_id
    )
