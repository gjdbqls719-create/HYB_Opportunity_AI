import pytest

from app.application.review import GetReviewSessionDetail, ReviewSessionQueryService
from app.founder_review_validation import run_validation
from app.infrastructure.review import SQLiteVerifiedSignalPersistence
from storage.price_history import DEFAULT_DATABASE_PATH


def test_local_validation_safety_gates(tmp_path):
    with pytest.raises(ValueError, match="production default"):
        run_validation(DEFAULT_DATABASE_PATH, confirm_local_demo=True)
    with pytest.raises(ValueError, match="confirm-local-demo"):
        run_validation(tmp_path / "demo.db", confirm_local_demo=False)


def test_file_backed_review_flow_and_restart_round_trip(tmp_path):
    database = tmp_path / "pr23c-demo.db"
    result = run_validation(database, confirm_local_demo=True)
    assert (result["status"], result["revision"]) == ("completed", 4)
    assert result["decision_connectivity"] == "bound:additional-decision-sources-required"
    restarted = SQLiteVerifiedSignalPersistence(database)
    try:
        detail = ReviewSessionQueryService(restarted.sessions, restarted.ledger).detail(GetReviewSessionDetail(result["session_id"]))
        assert detail.session.status.value == "completed"
        assert detail.session.revision == 4
        assert detail.candidates[0].status.value == "approved"
        assert restarted.ledger.get_verification_history(result["candidate_id"])[0].verification_id == result["verification_id"]
        signals = restarted.observations.get_latest_human_verified_external_signals(detail.candidates[0].context.market_observation_identity)
        assert tuple(signal.signal_id for signal in signals) == (result["external_signal_id"],)
        for transition in ("create", "start", "approve", "complete"):
            assert restarted.sessions.get_receipt(f"local-demo-pr23c-{transition}") is not None
    finally:
        restarted.close()


def test_prepare_mode_stops_before_mutation(tmp_path):
    result = run_validation(tmp_path / "prepared.db", confirm_local_demo=True, prepare_only=True)
    assert (result["status"], result["revision"]) == ("open", 1)
    assert result["verification_id"] is result["external_signal_id"] is None
