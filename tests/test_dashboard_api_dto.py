from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from decimal import Decimal
import inspect
import json

import pytest

from app.application.dashboard_api import (
    DASHBOARD_READ_MODEL_VERSION,
    DashboardApiAssembler,
    DashboardResponseDTO,
)
import app.application.dashboard_api.assembler as assembler_module
from app.domain.decision_engine import DecisionDimension, DecisionOutcome
from test_dashboard_read_model import read_model


def dto(outcome: DecisionOutcome = DecisionOutcome.INVEST) -> DashboardResponseDTO:
    return DashboardApiAssembler().assemble(read_model(outcome))


@pytest.mark.parametrize(
    ("outcome", "action"),
    (
        (DecisionOutcome.INVEST, "Proceed to Validation"),
        (DecisionOutcome.REVIEW, "Collect More Evidence"),
        (DecisionOutcome.REJECT, "Do Not Proceed"),
        (
            DecisionOutcome.INSUFFICIENT_EVIDENCE,
            "Acquire Required Evidence",
        ),
    ),
)
def test_outcome_dto_mapping(outcome: DecisionOutcome, action: str) -> None:
    value = dto(outcome)

    assert value.summary.outcome is outcome
    assert value.action.outcome is outcome
    assert value.action.primary_action == action
    assert value.action.secondary_action is None


def test_summary_action_and_metadata_preserve_read_model_values() -> None:
    source = read_model()
    value = DashboardApiAssembler().assemble(source)

    assert value.summary.confidence == source.summary_card.aggregate_confidence
    assert value.summary.summary_code is source.summary_card.summary_code
    assert value.summary.summary_text == source.summary_card.summary_text
    assert value.action.primary_action == source.action_card.primary_action
    assert value.metadata.generated_at == source.generated_at
    assert value.metadata.schema_version == source.schema_version
    assert value.metadata.policy_version == source.policy_version
    assert value.metadata.read_model_version == DASHBOARD_READ_MODEL_VERSION == "1.0"


def test_warning_mapping_preserves_text_severity_and_order() -> None:
    source = read_model(DecisionOutcome.REVIEW)
    value = DashboardApiAssembler().assemble(source)

    assert tuple(item.display_order for item in value.warnings) == tuple(
        item.display_order for item in source.warning_cards
    )
    for mapped, original in zip(value.warnings, source.warning_cards, strict=True):
        assert mapped.dimension is original.item.dimension
        assert mapped.severity is original.item.severity
        assert mapped.reason_code is original.item.reason_code
        assert mapped.text == original.item.default_text


def test_evidence_mapping_preserves_fixed_order_and_values() -> None:
    source = read_model()
    value = DashboardApiAssembler().assemble(source)

    assert tuple(item.dimension for item in value.evidence) == tuple(DecisionDimension)
    assert tuple(item.display_order for item in value.evidence) == (1, 2, 3, 4, 5)
    for mapped, original in zip(value.evidence, source.evidence_cards, strict=True):
        assert mapped.dimension is original.dimension
        assert mapped.availability is original.availability
        assert mapped.confidence == original.confidence
        assert mapped.freshness is original.freshness
        assert mapped.severity is original.severity


def test_dto_is_immutable_tuple_based_and_value_equal() -> None:
    first = dto()
    second = dto()

    assert first == second
    assert isinstance(first.warnings, tuple)
    assert isinstance(first.evidence, tuple)
    with pytest.raises(FrozenInstanceError):
        first.warnings = ()
    with pytest.raises(TypeError, match="tuple"):
        replace(first, warnings=list(first.warnings))


def test_assembler_and_serialization_are_deterministic() -> None:
    source = read_model()
    first = DashboardApiAssembler().assemble(source)
    second = DashboardApiAssembler().assemble(source)

    assert first == second
    assert first.to_dict() == second.to_dict()
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )


def test_to_dict_uses_exact_decimal_and_stable_enum_strings() -> None:
    value = dto()
    serialized = value.to_dict()

    assert value.summary.confidence == Decimal("0.875")
    assert serialized["summary"]["confidence"] == "0.875"
    assert serialized["summary"]["outcome"] == "invest"
    assert serialized["summary"]["summary_code"] == "invest_ready"
    assert serialized["evidence"][0]["dimension"] == "economics"
    assert serialized["evidence"][0]["confidence"] == "1"
    assert not isinstance(serialized["summary"]["confidence"], float)


def test_to_dict_datetime_is_timezone_aware_iso_8601() -> None:
    value = dto()
    serialized = value.to_dict()
    generated_at = serialized["metadata"]["generated_at"]

    assert generated_at == value.metadata.generated_at.isoformat()
    assert datetime.fromisoformat(generated_at).utcoffset() is not None


def test_assembler_does_not_mutate_source_read_model() -> None:
    source = read_model()
    before = repr(source)

    DashboardApiAssembler().assemble(source)

    assert repr(source) == before


def test_assembler_validates_input_type() -> None:
    with pytest.raises(TypeError, match="DashboardReadModel"):
        DashboardApiAssembler().assemble({})


def test_metadata_rejects_naive_datetime_and_blank_versions() -> None:
    value = dto()
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(value.metadata, generated_at=datetime(2026, 8, 3, 12))
    with pytest.raises(ValueError, match="schema_version"):
        replace(value.metadata, schema_version=" ")
    with pytest.raises(ValueError, match="read_model_version"):
        replace(value.metadata, read_model_version=" ")


def test_summary_confidence_rejects_missing_and_non_finite_values() -> None:
    value = dto().summary
    with pytest.raises(ValueError, match="required"):
        replace(value, confidence=None)
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(value, confidence=Decimal("NaN"))


def test_dto_layer_has_no_decision_execution_fastapi_or_ui_dependency() -> None:
    source = inspect.getsource(assembler_module).lower()

    for forbidden in (
        "decisionmatrix",
        "decisionpolicy",
        "decisionevaluationservice",
        "fastapi",
        "html",
        "javascript",
        "react",
        "vue",
        "repository",
    ):
        assert forbidden not in source
