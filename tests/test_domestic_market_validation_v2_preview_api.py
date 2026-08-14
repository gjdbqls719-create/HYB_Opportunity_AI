from dataclasses import replace
import sqlite3

from fastapi.testclient import TestClient

from app.application.domestic_market_validation_v2 import (
    ValidateDomesticMarketV2ForCapital,
)
from app.infrastructure.domestic_market_validation_v2 import (
    DomesticMarketValidationV2SourceRepositoryAdapter,
    SQLiteDomesticMarketValidationV2Repository,
)
from app.infrastructure.market_observation.demand_v2_sqlite_repository import (
    DemandV2CorruptionError,
)
from app.web import (
    app,
    get_domestic_market_validation_v2_source_preview,
)
import app.web as web_module
from test_domestic_market_validation_v2 import (
    EVALUATED_AT,
    Repository,
    _competition_publication,
    _competition_reference,
    _demand_publication,
)


PREVIEW_PATH = (
    "/api/v2/opportunities/{opportunity_id}/"
    "domestic-market-validations/source-manifest"
)


def test_openapi_exposes_read_only_domestic_market_validation_v2_source_preview():
    document = app.openapi()

    assert PREVIEW_PATH in document["paths"]
    assert set(document["paths"][PREVIEW_PATH]) == {"get"}
    operation = document["paths"][PREVIEW_PATH]["get"]
    assert "requestBody" not in operation
    assert {
        (parameter["in"], parameter["name"])
        for parameter in operation["parameters"]
    } == {
        ("path", "opportunity_id"),
        ("query", "competition_observation_id"),
        ("query", "demand_observation_id"),
    }


def _preview_service(*, competition=None, demand=None, repository=None):
    competition, fingerprint = (
        _competition_publication() if competition is None else competition
    )
    demand = _demand_publication() if demand is None else demand
    repository = repository or Repository(
        competition, demand, competition_fingerprint=fingerprint,
    )
    calls = []

    def forbidden_supplier():
        calls.append("called")
        raise AssertionError("source preview must not issue an assessment or time")

    service = ValidateDomesticMarketV2ForCapital(
        repository,
        assessment_id_generator=forbidden_supplier,
        evaluated_clock=forbidden_supplier,
    )
    return service, calls, competition, demand


def _get(client, *, competition_id="competition-observation-1", demand_id="obs-1"):
    return client.get(
        "/api/v2/opportunities/opportunity-1/domestic-market-validations/source-manifest",
        params={
            "competition_observation_id": competition_id,
            "demand_observation_id": demand_id,
        },
    )


def test_preview_returns_exact_resolved_manifest_and_fingerprint_without_policy_state():
    service, calls, competition, demand = _preview_service()
    expected = service.resolve_source_manifest(
        "opportunity-1", competition.observation_id, demand.observation.observation_id,
    )
    app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
        lambda: service
    )
    try:
        response = _get(TestClient(app))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["opportunity_id"] == "opportunity-1"
    assert body["source_manifest_fingerprint"] == expected.fingerprint
    assert body["source_manifest"]["target_binding"]["target_identity"] == {
        "domestic_selling_target_id": "dmv-v2-target-1",
        "market": "KR",
        "kind": "new_to_market_domestic_selling_target",
        "schema_version": expected.target_binding.target_identity.schema_version,
    }
    assert body["source_manifest"]["competition"]["observation_identity"] == {
        "observation_id": competition.observation_id,
        "identity_kind": competition.observation_identity.identity_kind.value,
        "identity_version": competition.observation_identity.identity_version,
    }
    assert body["source_manifest"]["competition"]["authority_fingerprint"] == (
        expected.competition.authority_fingerprint
    )
    assert body["source_manifest"]["demand"]["observation_id"] == (
        demand.observation.observation_id
    )
    assert body["source_manifest"]["demand"]["authority_fingerprint"] == (
        expected.demand.authority_fingerprint
    )
    assert body["source_manifest"]["schema_version"] == expected.schema_version
    assert calls == []
    forbidden = {
        "assessment_id", "state", "verification", "receipt", "blocked",
        "validated_for_capital", "capital_ready", "buy", "invest", "profit", "roi",
    }
    assert forbidden.isdisjoint(body)
    assert forbidden.isdisjoint(body["source_manifest"])
    assert "market_identity" not in str(body)


def test_repeated_preview_is_identical_and_creates_no_dmv_history_or_receipt(tmp_path):
    database = tmp_path / "preview.sqlite3"
    dmv_repository = SQLiteDomesticMarketValidationV2Repository(database)
    dmv_repository.close()
    service, calls, _, _ = _preview_service()
    app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
        lambda: service
    )
    try:
        client = TestClient(app)
        first = _get(client)
        second = _get(client)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert calls == []
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_v2_history"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_v2_receipts"
        ).fetchone()[0] == 0


def test_preview_serializes_exact_competition_reference_owned_by_demand():
    competition, fingerprint = _competition_publication()
    reference = _competition_reference(competition, fingerprint)
    demand = _demand_publication(competition_reference=reference)
    service, _, _, _ = _preview_service(
        competition=(competition, fingerprint), demand=demand,
    )
    app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
        lambda: service
    )
    try:
        response = _get(TestClient(app))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    actual = response.json()["source_manifest"]["demand"][
        "source_competition_cohort"
    ]
    assert actual["competition_observation_id"] == reference.competition_observation_id
    assert actual["authority_fingerprint"] == reference.authority_fingerprint
    assert actual["artifact_sha256"] == reference.artifact_sha256


def test_preview_maps_exact_missing_sources_to_not_found():
    service, _, _, _ = _preview_service()
    app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
        lambda: service
    )
    try:
        client = TestClient(app)
        missing_competition = _get(client, competition_id="missing")
        missing_demand = _get(client, demand_id="missing")
    finally:
        app.dependency_overrides.clear()

    assert missing_competition.status_code == 404
    assert missing_demand.status_code == 404


def test_preview_maps_malformed_persisted_source_to_bounded_unavailable():
    competition, fingerprint = _competition_publication()
    demand = _demand_publication()

    class CorruptRepository(Repository):
        def get_demand_publication(self, observation_id):
            raise DemandV2CorruptionError("internal persisted detail")

    service, _, _, _ = _preview_service(
        competition=(competition, fingerprint),
        demand=demand,
        repository=CorruptRepository(
            competition, demand, competition_fingerprint=fingerprint,
        ),
    )
    app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
        lambda: service
    )
    try:
        response = _get(TestClient(app))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Domestic Market Validation v2 source preview unavailable"
    }


def test_preview_maps_target_and_cross_authority_mismatches_to_conflict():
    competition, fingerprint = _competition_publication()
    demand = _demand_publication()
    repository = Repository(competition, demand, competition_fingerprint=fingerprint)
    repository.target_binding = replace(
        repository.target_binding, opportunity_id="different-opportunity",
    )
    target_service, _, _, _ = _preview_service(
        competition=(competition, fingerprint), demand=demand, repository=repository,
    )
    mismatched_reference = _competition_reference(
        competition, fingerprint, cohort_id="different-cohort",
    )
    mismatched_demand = _demand_publication(
        competition_reference=mismatched_reference,
    )
    reference_service, _, _, _ = _preview_service(
        competition=(competition, fingerprint), demand=mismatched_demand,
    )
    try:
        app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
            lambda: target_service
        )
        target_response = _get(TestClient(app))
        app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
            lambda: reference_service
        )
        reference_response = _get(TestClient(app))
    finally:
        app.dependency_overrides.clear()

    assert target_response.status_code == 409
    assert reference_response.status_code == 409


def test_production_source_adapter_is_read_only_exact_delegation():
    class Owner:
        def __init__(self):
            self.calls = []

        def get_target_binding(self, value):
            self.calls.append(("target", value)); return "target-binding"

        def get_publication_by_observation_id(self, value):
            self.calls.append(("competition", value)); return "competition-publication"

        def get_authority_fingerprint(self, value):
            self.calls.append(("fingerprint", value)); return "fingerprint"

        def get_publication(self, value):
            self.calls.append(("demand", value)); return "demand-publication"

    targets, competition, demand = Owner(), Owner(), Owner()
    adapter = DomesticMarketValidationV2SourceRepositoryAdapter(
        targets, competition, demand,
    )

    assert adapter.get_target_binding("opportunity") == "target-binding"
    assert adapter.get_competition_publication("competition") == "competition-publication"
    assert adapter.get_competition_authority_fingerprint("cohort") == "fingerprint"
    assert adapter.get_demand_publication("demand") == "demand-publication"
    assert adapter.get_demand_authority_fingerprint("demand") == "fingerprint"
    assert targets.calls == [("target", "opportunity")]
    assert competition.calls == [
        ("competition", "competition"), ("fingerprint", "cohort"),
    ]
    assert demand.calls == [("demand", "demand"), ("fingerprint", "demand")]


def test_unapproved_extra_query_values_are_rejected():
    service, _, _, _ = _preview_service()
    app.dependency_overrides[get_domestic_market_validation_v2_source_preview] = (
        lambda: service
    )
    try:
        client = TestClient(app)
        attempted_override = client.get(
            "/api/v2/opportunities/opportunity-1/domestic-market-validations/source-manifest",
            params={
                "competition_observation_id": "competition-observation-1",
                "demand_observation_id": "obs-1",
                "target_identity": "invented",
                "state": "validated_for_capital",
                "buy": "true",
                "profit": "999999",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert attempted_override.status_code == 422


def test_production_composition_uses_only_temp_source_stores_and_no_dmv_history(
    tmp_path, monkeypatch,
):
    database = tmp_path / "production-composition-preview.sqlite3"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)

    response = _get(TestClient(app), competition_id="missing", demand_id="missing")

    assert response.status_code == 404
    with sqlite3.connect(database) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "domestic_market_validation_v2_history" not in tables
    assert "domestic_market_validation_v2_receipts" not in tables
