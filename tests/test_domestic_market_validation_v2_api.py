from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.application.domestic_market_validation_v2 import (
    PersistDomesticMarketValidationV2ForCapital,
    ValidateDomesticMarketV2ForCapital,
)
from app.domain.market_intelligence.competition_v2 import CompetitionV2Availability
from app.domain.market_intelligence.demand_v2 import (
    DemandFamilyStatus,
    DemandV2Availability,
)
from app.infrastructure.domestic_market_validation import (
    SQLiteDomesticMarketValidationRepository,
)
from app.infrastructure.domestic_market_validation_v2 import (
    SQLiteDomesticMarketValidationV2Repository,
)
from app.web import (
    app,
    get_domestic_market_validation_v2_entry,
    get_domestic_market_validation_v2_source_preview,
)
import app.web as web_module
from test_domestic_market_validation_v2 import (
    EVALUATED_AT,
    Repository,
    VERIFIED_AT,
    _competition_publication,
    _competition_reference,
    _demand_publication,
)


FINAL_PATH = "/api/v2/opportunities/{opportunity_id}/domestic-market-validations"
FINAL_ROUTE = "/api/v2/opportunities/opportunity-1/domestic-market-validations"
PREVIEW_ROUTE = (
    "/api/v2/opportunities/opportunity-1/"
    "domestic-market-validations/source-manifest"
)
COMMITTED_AT = EVALUATED_AT + timedelta(minutes=1)


class Values:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        if self.calls >= len(self.values):
            raise AssertionError("supplier called more often than expected")
        value = self.values[self.calls]
        self.calls += 1
        return value


class CountingRepository(Repository):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def get_target_binding(self, opportunity_id):
        self.calls.append(("target", opportunity_id))
        return super().get_target_binding(opportunity_id)

    def get_competition_publication(self, observation_id):
        self.calls.append(("competition", observation_id))
        return super().get_competition_publication(observation_id)

    def get_competition_authority_fingerprint(self, cohort_id):
        self.calls.append(("competition_fingerprint", cohort_id))
        return super().get_competition_authority_fingerprint(cohort_id)

    def get_demand_publication(self, observation_id):
        self.calls.append(("demand", observation_id))
        return super().get_demand_publication(observation_id)

    def get_demand_authority_fingerprint(self, observation_id):
        self.calls.append(("demand_fingerprint", observation_id))
        return super().get_demand_authority_fingerprint(observation_id)


def _bundle(
    database,
    *,
    competition=None,
    demand=None,
    source=None,
    ids=None,
    evaluated=None,
    committed=None,
):
    competition, fingerprint = (
        _competition_publication() if competition is None else competition
    )
    demand = _demand_publication() if demand is None else demand
    source = source or CountingRepository(
        competition, demand, competition_fingerprint=fingerprint,
    )
    ids = ids or Values("dmv-v2-assessment-1")
    evaluated = evaluated or Values(EVALUATED_AT)
    committed = committed or Values(COMMITTED_AT)
    owner = ValidateDomesticMarketV2ForCapital(
        source,
        assessment_id_generator=ids,
        evaluated_clock=evaluated,
    )
    persistence = SQLiteDomesticMarketValidationV2Repository(database)
    entry = PersistDomesticMarketValidationV2ForCapital(
        persistence,
        owner,
        committed_clock=committed,
    )
    return {
        "competition": competition,
        "demand": demand,
        "source": source,
        "owner": owner,
        "persistence": persistence,
        "entry": entry,
        "ids": ids,
        "evaluated": evaluated,
        "committed": committed,
    }


def _counts(database):
    with sqlite3.connect(database) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "domestic_market_validation_v2_history",
                "domestic_market_validation_v2_receipts",
            )
        )


def _request(
    fingerprint,
    *,
    command_id="dmv-v2-command-1",
    current=True,
    competition_id="competition-observation-1",
    demand_id="obs-1",
    operator_id="founder",
):
    return {
        "command_id": command_id,
        "competition_observation_id": competition_id,
        "demand_observation_id": demand_id,
        "operator_id": operator_id,
        "verified_at": VERIFIED_AT.isoformat(),
        "current_use_confirmed": current,
        "reviewed_source_manifest_fingerprint": fingerprint,
        "requested_at": VERIFIED_AT.isoformat(),
    }


@contextmanager
def _client(bundle, *, preview=True):
    app.dependency_overrides[get_domestic_market_validation_v2_entry] = (
        lambda: bundle["entry"]
    )
    if preview:
        app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
            lambda: bundle["owner"]
        )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _preview(client):
    return client.get(PREVIEW_ROUTE, params={
        "competition_observation_id": "competition-observation-1",
        "demand_observation_id": "obs-1",
    })


def test_openapi_exposes_strict_v2_post_and_preserves_preview_and_v1():
    document = app.openapi()

    assert FINAL_PATH in document["paths"]
    assert set(document["paths"][FINAL_PATH]) == {"post"}
    assert "get" in document["paths"][f"{FINAL_PATH}/source-manifest"]
    assert "post" in document["paths"][
        "/api/v1/opportunities/{opportunity_id}/domestic-market-validations"
    ]
    operation = document["paths"][FINAL_PATH]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    request_schema = document["components"]["schemas"][request_ref.rsplit("/", 1)[1]]
    approved = {
        "command_id", "competition_observation_id", "demand_observation_id",
        "operator_id", "verified_at", "current_use_confirmed",
        "reviewed_source_manifest_fingerprint", "requested_at",
    }
    forbidden = {
        "target_identity", "identity", "market_identity", "state",
        "blocking_reasons", "assessment_id", "capital_ready", "buy", "invest",
        "profit", "roi", "margin", "source_manifest", "competition_evidence",
        "demand_evidence", "policy_name", "policy_version",
    }
    assert set(request_schema["properties"]) == approved
    assert set(request_schema["required"]) == approved
    assert request_schema["additionalProperties"] is False
    assert forbidden.isdisjoint(request_schema["properties"])
    response_ref = operation["responses"]["201"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    response_schema = document["components"]["schemas"][response_ref.rsplit("/", 1)[1]]
    assert set(response_schema["properties"]) >= {
        "assessment_id", "source_manifest", "source_manifest_fingerprint",
        "verification", "state", "blocking_reasons", "receipt", "replayed",
    }
    assert {
        "target_identity", "identity", "market_identity", "capital_ready",
        "buy", "invest", "profit", "roi", "margin", "competition_evidence",
        "demand_evidence",
    }.isdisjoint(response_schema["properties"])


@pytest.mark.parametrize(
    "extra",
    (
        {"target_identity": {"domestic_selling_target_id": "invented"}},
        {"identity": {"scope": "listing"}},
        {"state": "validated_for_capital"},
        {"buy": True, "invest": True, "profit": "1", "roi": "1", "margin": "1"},
        {"source_manifest": {"schema_version": "invented"}},
    ),
)
def test_final_request_rejects_every_unapproved_authority_field(tmp_path, extra):
    bundle = _bundle(tmp_path / "strict.db")
    payload = {**_request("a" * 64), **extra}
    with _client(bundle, preview=False) as client:
        response = client.post(FINAL_ROUTE, json=payload)
    bundle["persistence"].close()

    assert response.status_code == 422
    assert _counts(tmp_path / "strict.db") == (0, 0)


def test_preview_review_and_exact_post_persist_validated_authority(tmp_path):
    database = tmp_path / "approved-workflow.db"
    v1 = SQLiteDomesticMarketValidationRepository(database)
    v1.close()
    bundle = _bundle(database)

    with _client(bundle) as client:
        preview = _preview(client)
        assert preview.status_code == 200
        fingerprint = preview.json()["source_manifest_fingerprint"]
        response = client.post(FINAL_ROUTE, json=_request(fingerprint))

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "validated_for_capital"
    assert body["blocking_reasons"] == []
    assert body["source_manifest_fingerprint"] == fingerprint
    assert body["source_manifest"] == preview.json()["source_manifest"]
    assert body["source_manifest"]["target_binding"]["target_identity"][
        "domestic_selling_target_id"
    ] == "dmv-v2-target-1"
    assert body["source_manifest"]["competition"]["observation_identity"][
        "observation_id"
    ] == "competition-observation-1"
    assert body["source_manifest"]["demand"]["observation_id"] == "obs-1"
    assert body["verification"] == {
        "operator_id": "founder",
        "verified_at": VERIFIED_AT.isoformat().replace("+00:00", "Z"),
        "current_use_confirmed": True,
        "reviewed_source_manifest_fingerprint": fingerprint,
        "schema_version": "domestic-market-current-use-verification-v2",
    }
    assert body["receipt"]["source_manifest_fingerprint"] == fingerprint
    assert body["replayed"] is False
    assert _counts(database) == (1, 1)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_history"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_receipts"
        ).fetchone()[0] == 0
    assert "market_identity" not in str(body)
    bundle["persistence"].close()


@pytest.mark.parametrize(
    ("current", "fingerprint", "reason"),
    (
        (False, None, "current_use_verification_missing"),
        (True, "f" * 64, "reviewed_source_manifest_fingerprint_mismatch"),
    ),
)
def test_correct_sources_with_failed_verification_are_successful_blocked_publications(
    tmp_path, current, fingerprint, reason,
):
    database = tmp_path / f"blocked-{reason}.db"
    bundle = _bundle(database)
    with _client(bundle) as client:
        preview = _preview(client).json()
        reviewed = fingerprint or preview["source_manifest_fingerprint"]
        response = client.post(FINAL_ROUTE, json=_request(reviewed, current=current))

    assert response.status_code == 201
    assert response.json()["state"] == "blocked"
    assert reason in response.json()["blocking_reasons"]
    assert _counts(database) == (1, 1)
    bundle["persistence"].close()


@pytest.mark.parametrize("kind", ("competition", "demand"))
def test_incomplete_upstream_core_is_successful_blocked_publication(tmp_path, kind):
    competition = None
    demand = None
    expected = None
    if kind == "competition":
        competition = _competition_publication(CompetitionV2Availability.UNAVAILABLE)
        expected = "competition_v2_core_unavailable"
    else:
        demand = _demand_publication(
            market_intent_status=DemandFamilyStatus.PARTIAL,
            availability=DemandV2Availability.PARTIAL_CORE,
        )
        expected = "demand_v2_market_intent_incomplete"
    database = tmp_path / f"blocked-{kind}.db"
    bundle = _bundle(database, competition=competition, demand=demand)
    manifest = bundle["owner"].resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    with _client(bundle, preview=False) as client:
        response = client.post(FINAL_ROUTE, json=_request(manifest.fingerprint))

    assert response.status_code == 201
    assert response.json()["state"] == "blocked"
    assert expected in response.json()["blocking_reasons"]
    assert _counts(database) == (1, 1)
    bundle["persistence"].close()


@pytest.mark.parametrize(
    ("competition_id", "demand_id"),
    (("missing", "obs-1"), ("competition-observation-1", "missing")),
)
def test_missing_exact_source_is_404_and_persists_nothing(
    tmp_path, competition_id, demand_id,
):
    database = tmp_path / f"missing-{competition_id}-{demand_id}.db"
    bundle = _bundle(database)
    with _client(bundle, preview=False) as client:
        response = client.post(FINAL_ROUTE, json=_request(
            "a" * 64, competition_id=competition_id, demand_id=demand_id,
        ))

    assert response.status_code == 404
    assert _counts(database) == (0, 0)
    bundle["persistence"].close()


def test_target_and_demand_competition_reference_conflicts_are_409_without_assessment(
    tmp_path,
):
    competition, fingerprint = _competition_publication()
    demand = _demand_publication()
    target_source = CountingRepository(
        competition, demand, competition_fingerprint=fingerprint,
    )
    target_source.target_binding = replace(
        target_source.target_binding, opportunity_id="different-opportunity",
    )
    target_database = tmp_path / "target-conflict.db"
    target = _bundle(
        target_database,
        competition=(competition, fingerprint),
        demand=demand,
        source=target_source,
    )
    mismatched_demand = _demand_publication(competition_reference=(
        _competition_reference(competition, fingerprint, cohort_id="different-cohort")
    ))
    reference_database = tmp_path / "reference-conflict.db"
    reference = _bundle(
        reference_database,
        competition=(competition, fingerprint),
        demand=mismatched_demand,
    )

    with _client(target, preview=False) as client:
        target_response = client.post(FINAL_ROUTE, json=_request("a" * 64))
    with _client(reference, preview=False) as client:
        reference_response = client.post(FINAL_ROUTE, json=_request("a" * 64))

    assert target_response.status_code == reference_response.status_code == 409
    assert _counts(target_database) == _counts(reference_database) == (0, 0)
    target["persistence"].close()
    reference["persistence"].close()


def test_exact_http_replay_is_historical_and_skips_sources_ids_and_clocks(tmp_path):
    database = tmp_path / "replay.db"
    bundle = _bundle(database)
    manifest = bundle["owner"].resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    bundle["source"].calls.clear()
    with _client(bundle, preview=False) as client:
        first = client.post(FINAL_ROUTE, json=_request(manifest.fingerprint))
        source_calls = tuple(bundle["source"].calls)
        supplier_calls = (
            bundle["ids"].calls,
            bundle["evaluated"].calls,
            bundle["committed"].calls,
        )
        replay = client.post(FINAL_ROUTE, json=_request(manifest.fingerprint))

    assert first.status_code == 201
    assert replay.status_code == 200
    first_body, replay_body = first.json(), replay.json()
    assert replay_body["replayed"] is True
    for field in (
        "assessment_id", "source_manifest_fingerprint", "state",
        "blocking_reasons", "evaluated_at", "receipt",
    ):
        assert replay_body[field] == first_body[field]
    assert tuple(bundle["source"].calls) == source_calls
    assert (
        bundle["ids"].calls,
        bundle["evaluated"].calls,
        bundle["committed"].calls,
    ) == supplier_calls == (1, 1, 1)
    assert _counts(database) == (1, 1)
    bundle["persistence"].close()


def test_changed_replay_fingerprint_is_409_and_new_command_is_new_event(tmp_path):
    database = tmp_path / "replay-conflict-new-command.db"
    bundle = _bundle(
        database,
        ids=Values("assessment-one", "assessment-two"),
        evaluated=Values(EVALUATED_AT, EVALUATED_AT),
        committed=Values(COMMITTED_AT, COMMITTED_AT + timedelta(seconds=1)),
    )
    manifest = bundle["owner"].resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    with _client(bundle, preview=False) as client:
        first = client.post(FINAL_ROUTE, json=_request(manifest.fingerprint))
        conflict = client.post(FINAL_ROUTE, json=_request("f" * 64))
        second = client.post(FINAL_ROUTE, json=_request(
            manifest.fingerprint, command_id="dmv-v2-command-2",
        ))

    assert first.status_code == second.status_code == 201
    assert conflict.status_code == 409
    assert first.json()["assessment_id"] != second.json()["assessment_id"]
    assert first.json()["source_manifest"] == second.json()["source_manifest"]
    assert _counts(database) == (2, 2)
    bundle["persistence"].close()


def test_unsupported_persisted_version_is_bounded_503(tmp_path):
    database = tmp_path / "unsupported.db"
    bundle = _bundle(database)
    manifest = bundle["owner"].resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    with _client(bundle, preview=False) as client:
        assert client.post(FINAL_ROUTE, json=_request(manifest.fingerprint)).status_code == 201
    bundle["persistence"].close()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DROP TRIGGER trg_domestic_market_validation_v2_history_no_update"
        )
        connection.execute(
            "UPDATE domestic_market_validation_v2_history "
            "SET schema_version='unsupported'"
        )
        connection.execute(
            "CREATE TRIGGER trg_domestic_market_validation_v2_history_no_update "
            "BEFORE UPDATE ON domestic_market_validation_v2_history "
            "BEGIN SELECT RAISE(ABORT, 'domestic_market_validation_v2_history is append-only'); END"
        )
        connection.commit()

    restarted = _bundle(database)
    with _client(restarted, preview=False) as client:
        response = client.post(FINAL_ROUTE, json=_request(manifest.fingerprint))

    assert response.status_code == 503
    assert response.json() == {"detail": "Domestic Market Validation v2 unavailable"}
    assert _counts(database) == (1, 1)
    restarted["persistence"].close()


def test_corrupted_persisted_payload_is_bounded_503(tmp_path):
    database = tmp_path / "corrupted.db"
    bundle = _bundle(database)
    manifest = bundle["owner"].resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    with _client(bundle, preview=False) as client:
        assert client.post(FINAL_ROUTE, json=_request(manifest.fingerprint)).status_code == 201
    bundle["persistence"].close()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DROP TRIGGER trg_domestic_market_validation_v2_history_no_update"
        )
        connection.execute(
            "UPDATE domestic_market_validation_v2_history "
            "SET integrity_fingerprint=?",
            ("0" * 64,),
        )
        connection.execute(
            "CREATE TRIGGER trg_domestic_market_validation_v2_history_no_update "
            "BEFORE UPDATE ON domestic_market_validation_v2_history "
            "BEGIN SELECT RAISE(ABORT, 'domestic_market_validation_v2_history is append-only'); END"
        )
        connection.commit()

    restarted = _bundle(database)
    with _client(restarted, preview=False) as client:
        response = client.post(FINAL_ROUTE, json=_request(manifest.fingerprint))

    assert response.status_code == 503
    assert response.json() == {"detail": "Domestic Market Validation v2 unavailable"}
    assert _counts(database) == (1, 1)
    restarted["persistence"].close()


def test_real_production_composition_uses_temp_database_and_creates_no_assessment_on_404(
    tmp_path, monkeypatch,
):
    database = tmp_path / "production-composition.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            response = client.post(FINAL_ROUTE, json=_request("a" * 64))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert _counts(database) == (0, 0)
    with sqlite3.connect(database) as connection:
        names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "domestic_market_validation_history" not in names
    assert "domestic_market_validation_receipts" not in names


def test_production_dependency_closes_every_request_owned_repository(monkeypatch):
    resources = []

    class Resource:
        def __init__(self, *_args, **_kwargs):
            self.closed = False
            resources.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(web_module, "SQLiteValidationQueueRepository", Resource)
    monkeypatch.setattr(web_module, "SQLiteCompetitionV2Repository", Resource)
    monkeypatch.setattr(web_module, "SQLiteDemandV2Repository", Resource)
    monkeypatch.setattr(
        web_module, "SQLiteDomesticMarketValidationV2Repository", Resource,
    )

    dependency = get_domestic_market_validation_v2_entry()
    entry = next(dependency)
    assert isinstance(entry, PersistDomesticMarketValidationV2ForCapital)
    dependency.close()

    assert len(resources) == 4
    assert all(resource.closed for resource in resources)
