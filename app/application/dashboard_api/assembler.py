from __future__ import annotations

from app.application.dashboard import DashboardReadModel
from app.application.dashboard_api.models import (
    DashboardActionDTO,
    DashboardEvidenceDTO,
    DashboardMetadataDTO,
    DashboardResponseDTO,
    DashboardSummaryDTO,
    DashboardWarningDTO,
)


DASHBOARD_READ_MODEL_VERSION = "1.0"


class DashboardApiAssembler:
    def assemble(self, read_model: DashboardReadModel) -> DashboardResponseDTO:
        if not isinstance(read_model, DashboardReadModel):
            raise TypeError("read_model must be DashboardReadModel")
        summary = read_model.summary_card
        action = read_model.action_card
        return DashboardResponseDTO(
            summary=DashboardSummaryDTO(
                outcome=summary.outcome,
                confidence=summary.aggregate_confidence,
                summary_code=summary.summary_code,
                summary_text=summary.summary_text,
            ),
            action=DashboardActionDTO(
                outcome=action.outcome,
                primary_action=action.primary_action,
                secondary_action=action.secondary_action,
            ),
            warnings=tuple(
                DashboardWarningDTO(
                    dimension=value.item.dimension,
                    severity=value.item.severity,
                    reason_code=value.item.reason_code,
                    text=value.item.default_text,
                    display_order=value.display_order,
                )
                for value in read_model.warning_cards
            ),
            evidence=tuple(
                DashboardEvidenceDTO(
                    dimension=value.dimension,
                    availability=value.availability,
                    confidence=value.confidence,
                    freshness=value.freshness,
                    severity=value.severity,
                    display_order=value.display_order,
                )
                for value in read_model.evidence_cards
            ),
            metadata=DashboardMetadataDTO(
                generated_at=read_model.generated_at,
                schema_version=read_model.schema_version,
                policy_version=read_model.policy_version,
                read_model_version=DASHBOARD_READ_MODEL_VERSION,
            ),
        )
