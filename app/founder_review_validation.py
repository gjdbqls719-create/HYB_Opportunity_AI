"""Explicit local-only Founder Review validation harness."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.application.review import ApproveCandidateCommand, CompleteReviewCommand, CreateReviewSession, GetReviewSessionDetail, ReviewCommandContext, ReviewSessionQueryService, ReviewWorkflowService, StartReviewCommand
from app.domain.market_intelligence import ArtifactOrigin, ArtifactReference, ArtifactType, ExternalSignalDirection, ExternalSignalSourceType, MarketObservationIdentity, MarketObservationScope, OCRCandidate, OCRField
from app.infrastructure.review import SQLiteVerifiedSignalPersistence
from app.application.opportunity_validation import AddToValidationQueueCommand, OpportunityValidationService
from storage.price_history import DEFAULT_DATABASE_PATH

DEMO_PREFIX = "local-demo-pr23c"
BASE_TIME = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)


def _safe_database_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path == Path(DEFAULT_DATABASE_PATH).resolve():
        raise ValueError("local validation refuses the production default database")
    if path.exists():
        raise ValueError("local validation requires a new database file")
    return path


def run_validation(database: str | Path, *, confirm_local_demo: bool, prepare_only: bool = False, opportunity_only: bool = False) -> dict[str, object]:
    if not confirm_local_demo:
        raise ValueError("--confirm-local-demo is required")
    path = _safe_database_path(database)
    artifact_id, candidate_id, session_id = (f"{DEMO_PREFIX}-{name}" for name in ("artifact", "candidate", "session"))
    operator_id = f"{DEMO_PREFIX}-operator"
    identity = MarketObservationIdentity(
        scope=MarketObservationScope.LISTING, market="local-demo-market", marketplace="local-demo-marketplace",
        canonical_product_id=None, marketplace_item_id=f"{DEMO_PREFIX}-item", normalized_query=None,
        category=None, variant_identity=None, condition=None,
        window_started_at=BASE_TIME - timedelta(hours=1), window_ended_at=BASE_TIME,
    )
    artifact = ArtifactReference(
        artifact_id=artifact_id, artifact_type=ArtifactType.SCREENSHOT, artifact_origin=ArtifactOrigin.MANUAL,
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT, sha256="0" * 64, captured_at=BASE_TIME,
        width=1280, height=720, mime_type="image/png", file_size=0, schema_version="artifact-reference-v1",
    )
    candidate = OCRCandidate(candidate_id, artifact, OCRField.SEARCH_VOLUME, "1,234", 1234, Decimal("0.91"), BASE_TIME, "ocr-candidate-v1")
    persistence = SQLiteVerifiedSignalPersistence(path)
    try:
        OpportunityValidationService(queue_repository=persistence.opportunities, lifecycle_repository=persistence.opportunities).add(
            AddToValidationQueueCommand(opportunity_id=f"{DEMO_PREFIX}-opportunity", discovery_reference=f"local-demo-marketplace:{DEMO_PREFIX}-item",
                marketplace="local-demo-marketplace", title="Local demo validation opportunity", admission_recommendation="WATCH",
                admission_score=70, admission_roi=20, currency="USD", admission_safety_status="READY",
                operator_id=operator_id, reason="explicit local demo validation", captured_at=BASE_TIME,
                market_observation_identity=identity))
        persistence.ledger.save_candidate(candidate)
        if opportunity_only:
            return {"database":str(path),"demo_data":True,"mode":"opportunity","opportunity_id":f"{DEMO_PREFIX}-opportunity","candidate_id":candidate_id}
        workflow = ReviewWorkflowService(persistence.ledger, observation_repository=persistence.observations, persistence=persistence)
        session = workflow.create_session(CreateReviewSession(
            session_id, artifact_id, (candidate_id,), operator_id, BASE_TIME + timedelta(minutes=1),
            command_id=f"{DEMO_PREFIX}-create",
            contexts=(ReviewCommandContext(session_id, candidate_id, identity, "search_volume", ExternalSignalDirection.POSITIVE, artifact_id, BASE_TIME + timedelta(minutes=1)),),
            opportunity_id=f"{DEMO_PREFIX}-opportunity",
        ))
        signal_id = verification_id = None
        if not prepare_only:
            session = workflow.start_review(StartReviewCommand(session_id, 1, f"{DEMO_PREFIX}-start", operator_id, BASE_TIME + timedelta(minutes=2)))
            approved = workflow.approve_candidate(ApproveCandidateCommand(
                session_id=session_id, candidate_id=candidate_id, expected_revision=2,
                command_id=f"{DEMO_PREFIX}-approve", verification_id=f"{DEMO_PREFIX}-verification",
                operator_id=operator_id, verified_at=BASE_TIME + timedelta(minutes=3), signal_id=f"{DEMO_PREFIX}-signal",
            ))
            session = workflow.complete_review(CompleteReviewCommand(session_id, 3, f"{DEMO_PREFIX}-complete", operator_id, BASE_TIME + timedelta(minutes=4)))
            signal_id, verification_id = approved.signal.signal_id, approved.verification.verification_id
        detail = ReviewSessionQueryService(persistence.sessions, persistence.ledger).detail(GetReviewSessionDetail(session_id))
        return {"database": str(path), "demo_data": True, "mode": "prepare" if prepare_only else "complete",
                "session_id": session_id, "status": detail.session.status.value, "revision": detail.session.revision,
                "candidate_id": candidate_id, "verification_id": verification_id, "external_signal_id": signal_id,
                "decision_connectivity": "bound:additional-decision-sources-required"}
    finally:
        persistence.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated PR23-C local demo Review database")
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-local-demo", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--opportunity-only", action="store_true")
    args = parser.parse_args()
    try:
        result = run_validation(args.database, confirm_local_demo=args.confirm_local_demo, prepare_only=args.prepare_only, opportunity_only=args.opportunity_only)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
