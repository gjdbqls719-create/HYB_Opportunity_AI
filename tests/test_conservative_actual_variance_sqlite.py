from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.conservative_actual_variance import (
    MalformedConservativeActualVariancePersistenceError,
    SQLiteConservativeActualVarianceRepository,
)
from app.web import app
from test_conservative_actual_variance_production_api import _variance_journey
from test_o2_economics_production_chain_api import economics_chain_client


def test_sqlite_restart_round_trip_append_only_and_exact_cardinality(
    economics_chain_client,
):
    result = _variance_journey(economics_chain_client)
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201, response.text
    variance_id = response.json()["variance_id"]
    with SQLiteConservativeActualVarianceRepository(result["database"]) as repository:
        restored = repository.get_variance(variance_id)
        assert restored.variance_id == variance_id
        assert restored.source_manifest.conservative_result_id == (
            result["variance_payload"]["conservative_economics_result_id"]
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(
                "UPDATE conservative_actual_variance_history SET comparison_state='not_comparable'"
            )
        repository._connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(
                "DELETE FROM conservative_actual_variance_history"
            )
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_receipts"
        ).fetchone()[0] == 1


def test_sqlite_malformed_payload_fails_closed(economics_chain_client):
    result = _variance_journey(economics_chain_client)
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201
    with sqlite3.connect(result["database"]) as connection:
        connection.execute("DROP TRIGGER trg_conservative_actual_variance_history_no_update")
        connection.execute(
            "UPDATE conservative_actual_variance_history SET payload_json='{}'"
        )
    with SQLiteConservativeActualVarianceRepository(result["database"]) as repository:
        with pytest.raises(MalformedConservativeActualVariancePersistenceError):
            repository.get_variance(response.json()["variance_id"])


@pytest.mark.parametrize(
    "mutation",
    (
        "metric_arithmetic",
        "favorability",
        "relative_variance",
        "percentage_points",
        "calibration_state",
        "source_pair",
        "source_fingerprint",
    ),
)
def test_sqlite_semantically_malformed_history_fails_closed(
    economics_chain_client,
    mutation,
):
    result = _variance_journey(economics_chain_client)
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201
    with sqlite3.connect(result["database"]) as connection:
        encoded = connection.execute(
            "SELECT payload_json FROM conservative_actual_variance_history"
        ).fetchone()[0]
        payload = json.loads(encoded)
        if mutation == "metric_arithmetic":
            payload["core_metrics"][0]["actual_value"] = "999"
        elif mutation == "favorability":
            payload["core_metrics"][0]["favorability"] = "unavailable"
        elif mutation == "relative_variance":
            payload["core_metrics"][0]["relative_variance_percent"] = "999"
        elif mutation == "percentage_points":
            payload["core_metrics"][6]["variance_percentage_points"] = "999"
        elif mutation == "calibration_state":
            payload["calibration_eligibility"] = "ineligible"
        elif mutation == "source_pair":
            payload["source_manifest"]["source_pair_fingerprint"] = "0" * 64
        elif mutation == "source_fingerprint":
            payload["source_manifest"]["conservative_source_fingerprint"] = "0" * 64
        replacement = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        integrity = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
        connection.execute("DROP TRIGGER trg_conservative_actual_variance_history_no_update")
        connection.execute(
            "UPDATE conservative_actual_variance_history SET payload_json=?, integrity_fingerprint=?",
            (replacement, integrity),
        )
    with SQLiteConservativeActualVarianceRepository(result["database"]) as repository:
        with pytest.raises(MalformedConservativeActualVariancePersistenceError):
            repository.get_variance(response.json()["variance_id"])


def test_sqlite_orphan_receipt_fails_closed(economics_chain_client):
    result = _variance_journey(economics_chain_client)
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201
    with sqlite3.connect(result["database"]) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DROP TRIGGER trg_conservative_actual_variance_history_no_delete")
        connection.execute("DELETE FROM conservative_actual_variance_history")
    with SQLiteConservativeActualVarianceRepository(result["database"]) as repository:
        with pytest.raises(MalformedConservativeActualVariancePersistenceError):
            repository.validate_replay(
                result["variance_payload"]["command_id"],
                repository._receipt_row(result["variance_payload"]["command_id"])[
                    "command_fingerprint"
                ],
            )


def test_sqlite_reads_are_pure_and_external_connection_is_not_owned(
    economics_chain_client,
):
    result = _variance_journey(economics_chain_client)
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201
    connection = sqlite3.connect(result["database"])
    repository = SQLiteConservativeActualVarianceRepository(connection=connection)
    before = connection.total_changes
    assert repository.get_variance(response.json()["variance_id"]) is not None
    assert repository.find_by_scope(
        connection.execute(
            "SELECT scope_fingerprint FROM conservative_actual_variance_history"
        ).fetchone()[0]
    ) is not None
    assert connection.total_changes == before
    repository.close()
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()


def test_sqlite_same_command_concurrency_converges(economics_chain_client):
    result = _variance_journey(economics_chain_client)

    def invoke():
        return TestClient(app).post(result["variance_route"], json=result["variance_payload"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _value: invoke(), range(2)))
    assert {response.status_code for response in responses} <= {200, 201}
    assert len({response.json()["variance_id"] for response in responses}) == 1
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_receipts"
        ).fetchone()[0] == 1


def test_sqlite_commit_failure_rolls_back_and_api_retry_succeeds(
    economics_chain_client,
    monkeypatch,
):
    result = _variance_journey(economics_chain_client)
    real_repository = SQLiteConservativeActualVarianceRepository
    captured = []

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def _commit(self):
            raise sqlite3.OperationalError("private commit detail")

    monkeypatch.setattr(web_module, "SQLiteConservativeActualVarianceRepository", FailingRepository)
    failed = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert failed.status_code == 503
    assert "private commit detail" not in failed.text
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_history"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_receipts"
        ).fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")

    monkeypatch.setattr(web_module, "SQLiteConservativeActualVarianceRepository", real_repository)
    retry = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert retry.status_code == 201, retry.text
