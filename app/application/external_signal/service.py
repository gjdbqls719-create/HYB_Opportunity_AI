from __future__ import annotations

from app.application.external_signal.models import ExternalSignalTrustError
from app.application.external_signal.use_cases import (
    CreateExternalSignal,
    CreateOCRCandidate,
    VerifyOCRCandidate,
)
from app.domain.market_intelligence import (
    ExternalMarketSignal,
    ExternalSignalSourceType,
    HumanVerification,
    MarketEvidence,
    MarketEvidenceStatus,
    OCRCandidate,
)


class ExternalSignalTrustService:
    """Pure coordinator for the artifact-to-verified-signal trust chain."""

    def create_ocr_candidate(self, command: CreateOCRCandidate) -> OCRCandidate:
        return OCRCandidate(
            candidate_id=command.candidate_id,
            artifact=command.artifact,
            field_name=command.field_name,
            raw_text=command.raw_text,
            normalized_value=command.normalized_value,
            confidence=command.confidence,
            captured_at=command.captured_at,
            schema_version=command.schema_version,
        )

    def verify_ocr_candidate(self, command: VerifyOCRCandidate) -> HumanVerification:
        if command.verified_at < command.candidate.captured_at:
            raise ExternalSignalTrustError("verification cannot precede OCR candidate")
        return HumanVerification(
            verification_id=command.verification_id,
            candidate_id=command.candidate.candidate_id,
            verified_value=command.verified_value,
            operator_id=command.operator_id,
            verified_at=command.verified_at,
            comment=command.comment,
            schema_version=command.schema_version,
        )

    def create_external_signal(self, command: CreateExternalSignal) -> ExternalMarketSignal:
        verification = command.verification
        if verification is None:
            raise ExternalSignalTrustError("human verification is required")
        if verification.candidate_id != command.candidate.candidate_id:
            raise ExternalSignalTrustError("verification must belong to OCR candidate")
        if verification.verified_at < command.candidate.captured_at:
            raise ExternalSignalTrustError("verification cannot precede OCR candidate")
        source_type = command.candidate.artifact.source_type
        if source_type is ExternalSignalSourceType.OCR_CANDIDATE:
            raise ExternalSignalTrustError(
                "OCR candidate source cannot represent a human-verified signal"
            )
        artifact = command.candidate.artifact
        evidence = MarketEvidence(
            value=verification.verified_value,
            source=f"artifact:{artifact.artifact_origin.value}",
            reference=artifact.artifact_id,
            observed_at=verification.verified_at,
            status=MarketEvidenceStatus.HUMAN_VERIFIED,
            confidence=command.confidence,
            market=command.identity.market,
            marketplace=command.identity.marketplace,
            collection_method="human_verification",
            schema_version="market-evidence-v1",
            keyword=command.identity.normalized_query,
            category=command.identity.category,
            marketplace_item_id=command.identity.marketplace_item_id,
            canonical_product_id=command.identity.canonical_product_id,
            unit=None,
        )
        return ExternalMarketSignal(
            signal_id=command.signal_id,
            identity=command.identity,
            source_type=source_type,
            signal_name=command.signal_name,
            signal_direction=command.signal_direction,
            evidence=evidence,
            captured_at=artifact.captured_at,
            schema_version=command.schema_version,
            verified_at=verification.verified_at,
            operator_id=verification.operator_id,
            artifact_reference=artifact.artifact_id,
        )
