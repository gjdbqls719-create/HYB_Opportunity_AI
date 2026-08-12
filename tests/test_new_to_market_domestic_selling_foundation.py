from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.candidate_promotion import PromoteOpportunityCandidateV2Command
from app.application.domestic_selling_opportunity import (
    DomesticSellingOpportunityCardinalityConflictError,
)
from app.application.new_to_market_domestic_selling import (
    AdmitNewToMarketDomesticSellingOpportunity,
    AdmitNewToMarketDomesticSellingOpportunityCommand,
    NewToMarketDomesticSellingCardinalityConflictError,
    NewToMarketDomesticSellingLineageError,
    NewToMarketDomesticSellingReplayConflictError,
    NewToMarketDomesticSellingSourceNotFoundError,
)
from app.domain.opportunity import (
    BoundedKRSearchConclusion,
    BoundedKRSearchManifest,
    BoundedKRSearchScopeKind,
    NewToMarketDomesticSellingTargetIdentity,
    OpportunityLifecycleStatus,
)
from app.infrastructure.domestic_selling_opportunity import (
    SQLiteDomesticSellingOpportunityAdmissionRepository,
)
from app.infrastructure.new_to_market_domestic_selling import (
    MalformedNewToMarketDomesticSellingPersistenceError,
    NewToMarketDomesticSellingHistoryError,
    SQLiteNewToMarketDomesticSellingAdmissionRepository,
)
from app.web import app
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_promotion_v2 import _close, _prepared_v2, _v2_payload
from test_domestic_selling_opportunity_admission import (
    Calls,
    command as existing_product_command,
)
from test_domestic_selling_opportunity_sqlite import make_owner as existing_owner


PERFORMED_AT = ISSUED_AT + timedelta(minutes=3)
VERIFIED_AT = ISSUED_AT + timedelta(minutes=4)
REQUESTED_AT = ISSUED_AT + timedelta(minutes=5)


def _prepare_o1(tmp_path):
    resources = _prepared_v2(tmp_path)
    payload = _v2_payload()
    payload["requested_at"] = datetime.fromisoformat(payload["requested_at"])
    result = resources[4].execute_v2(
        PromoteOpportunityCandidateV2Command(**payload)
    )
    return tmp_path / "promotion-v2.db", resources, result


def _search(**changes):
    values = {
        "searched_channels": ("coupang", "naver-shopping"),
        "scope_kind": BoundedKRSearchScopeKind.QUERY,
        "scope_value": "car seat organizer",
        "performed_at": PERFORMED_AT,
        "operator_id": "founder",
        "evidence_references": (
            "evidence/kr/coupang-search-2026-08-12.png",
            "evidence/kr/naver-search-2026-08-12.png",
        ),
        "conclusion": BoundedKRSearchConclusion.EXACT_KR_IDENTITY_NOT_ESTABLISHED,
    }
    values.update(changes)
    return BoundedKRSearchManifest(**values)


def _command(**changes):
    values = {
        "command_id": "new-market-command-1",
        "source_opportunity_id": "opportunity-v2-1",
        "source_product_snapshot_id": "product-snapshot-1",
        "operator_id": "founder",
        "decision_reason": (
            "evaluate the exact persisted source product as a pre-listing KR target"
        ),
        "search_manifest": _search(),
        "verified_at": VERIFIED_AT,
        "requested_at": REQUESTED_AT,
    }
    values.update(changes)
    return AdmitNewToMarketDomesticSellingOpportunityCommand(**values)


def _owner(repository, *, fail=False):
    if fail:
        blocked = Calls(AssertionError("server identity or clock must not run"))
        return AdmitNewToMarketDomesticSellingOpportunity(
            repository,
            opportunity_id_generator=blocked,
            target_id_generator=blocked,
            admission_id_generator=blocked,
            admitted_clock=blocked,
            committed_clock=blocked,
        ), blocked
    return (
        AdmitNewToMarketDomesticSellingOpportunity(
            repository,
            opportunity_id_generator=Calls("new-market-o2-1"),
            target_id_generator=Calls("new-market-target-1"),
            admission_id_generator=Calls("new-market-admission-1"),
            admitted_clock=Calls(REQUESTED_AT + timedelta(minutes=1)),
            committed_clock=Calls(REQUESTED_AT + timedelta(minutes=2)),
        ),
        None,
    )


def _api_payload(**changes):
    value = {
        "command_id": "new-market-command-1",
        "source_product_snapshot_id": "product-snapshot-1",
        "operator_id": "founder",
        "decision_reason": (
            "evaluate the exact persisted source product as a pre-listing KR target"
        ),
        "bounded_kr_search": {
            "searched_channels": ["coupang", "naver-shopping"],
            "scope_kind": "query",
            "scope_value": "car seat organizer",
            "performed_at": PERFORMED_AT.isoformat(),
            "operator_id": "founder",
            "evidence_references": [
                "evidence/kr/coupang-search-2026-08-12.png",
                "evidence/kr/naver-search-2026-08-12.png",
            ],
            "conclusion": "exact_kr_identity_not_established",
        },
        "verified_at": VERIFIED_AT.isoformat(),
        "requested_at": REQUESTED_AT.isoformat(),
        "policy_name": "new-to-market-domestic-selling-admission",
        "policy_version": "1.0.0",
    }
    value.update(changes)
    return value


def test_new_to_market_openapi_contract_is_distinct_from_adr_0049():
    document = TestClient(app).get("/openapi.json").json()
    route = (
        "/api/v1/opportunities/{source_opportunity_id}/"
        "new-to-market-domestic-selling-admissions"
    )

    assert route in document["paths"]
    operation = document["paths"][route]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"].rsplit("/", 1)[-1]
    properties = document["components"]["schemas"][request_schema]["properties"]

    assert request_schema == "NewToMarketDomesticSellingOpportunityAdmissionRequest"
    assert {
        "product_equivalence_confirmed",
        "target_market_identity",
        "marketplace_item_id",
        "canonical_product_id",
        "domestic_selling_target_id",
        "domestic_opportunity_id",
        "admitted_at",
        "committed_at",
    }.isdisjoint(properties)


def test_target_and_bounded_search_domain_are_kr_only_and_narrow():
    target = NewToMarketDomesticSellingTargetIdentity("opaque-target")
    assert target.market == "KR"
    assert target.kind.value == "new_to_market_domestic_selling_target"
    assert not hasattr(target, "marketplace_item_id")
    assert not hasattr(target, "canonical_product_id")
    assert _search().conclusion.value == "exact_kr_identity_not_established"

    with pytest.raises(ValueError):
        NewToMarketDomesticSellingTargetIdentity("opaque-target", market="US")
    with pytest.raises(ValueError):
        _search(conclusion="no_equivalent_product_exists_anywhere_in_korea")
    with pytest.raises(ValueError):
        _search(searched_channels=())


def test_fresh_admission_reconstructs_exact_v2_source_and_creates_target_o2(tmp_path):
    path, resources, promotion = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        result = _owner(repository)[0].execute(_command())

        assert result.replayed is False
        assert result.lifecycle.status is OpportunityLifecycleStatus.DISCOVERED
        assert result.lifecycle.version == 1
        assert result.lifecycle.opportunity_id == "new-market-o2-1"
        assert result.target_binding.target_identity.domestic_selling_target_id == (
            "new-market-target-1"
        )
        assert repository.get_market_identity_binding("new-market-o2-1") is None
        assert repository.get_target_binding("new-market-o2-1") == result.target_binding
        source = result.admission.source_manifest
        assert source.source_opportunity_identity.opportunity_id == promotion.binding.opportunity_id
        assert source.candidate_opportunity_binding_id == promotion.binding.binding_id
        assert source.promotion_admission_id == promotion.item.admission_basis.admission_id
        assert source.product_snapshot_ids == (
            "product-snapshot-1",
            "product-snapshot-2",
        )
        assert source.representative_product_snapshot_id == "product-snapshot-1"
        assert source.selected_source_observation_id == "observation-1"
        assert repository._connection.in_transaction is False
    finally:
        repository.close()
        _close(resources)


def test_exact_replay_and_subject_alias_do_not_issue_identity_or_call_clocks(tmp_path):
    path, resources, _ = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        first = _owner(repository)[0].execute(_command())
        replay_owner, replay_calls = _owner(repository, fail=True)
        replay = replay_owner.execute(_command())
        alias = replay_owner.execute(_command(command_id="new-market-command-alias"))

        assert replay == replace(first, replayed=True)
        assert alias.admission == first.admission
        assert alias.target_binding == first.target_binding
        assert alias.lifecycle == first.lifecycle
        assert alias.replayed is True
        assert replay_calls.calls == 0
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM new_to_market_domestic_selling_admission_history"
        ).fetchone()[0] == 1
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM new_to_market_domestic_selling_admission_receipts"
        ).fetchone()[0] == 2
    finally:
        repository.close()
        _close(resources)


def test_changed_command_and_changed_subject_conflict(tmp_path):
    path, resources, _ = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        _owner(repository)[0].execute(_command())
        with pytest.raises(NewToMarketDomesticSellingReplayConflictError):
            _owner(repository)[0].execute(
                _command(decision_reason="changed decision")
            )
        with pytest.raises(NewToMarketDomesticSellingCardinalityConflictError):
            _owner(repository)[0].execute(
                _command(
                    command_id="new-command",
                    search_manifest=_search(scope_value="changed query"),
                )
            )
    finally:
        repository.close()
        _close(resources)


@pytest.mark.parametrize(
    "changes,error",
    (
        ({"source_opportunity_id": "missing"}, NewToMarketDomesticSellingSourceNotFoundError),
        ({"source_product_snapshot_id": "missing"}, NewToMarketDomesticSellingSourceNotFoundError),
    ),
)
def test_missing_exact_source_fails_closed(tmp_path, changes, error):
    path, resources, _ = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        with pytest.raises(error):
            _owner(repository)[0].execute(_command(**changes))
    finally:
        repository.close()
        _close(resources)


def test_partial_or_reordered_promotion_source_is_rejected(tmp_path):
    path, resources, _ = _prepare_o1(tmp_path)
    connection = resources[3]._connection
    connection.execute(
        "DROP TRIGGER trg_opportunity_candidate_promotion_v2_source_history_no_update"
    )
    connection.execute(
        "UPDATE opportunity_candidate_promotion_v2_source_history "
        "SET ordered_product_snapshot_ids_json='[\"product-snapshot-2\",\"product-snapshot-1\"]'"
    )
    connection.commit()
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        with pytest.raises(NewToMarketDomesticSellingLineageError):
            _owner(repository)[0].execute(_command())
    finally:
        repository.close()
        _close(resources)


def test_restart_reconstruction_append_only_and_corruption_detection(tmp_path):
    path, resources, _ = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    first = _owner(repository)[0].execute(_command())
    for table in (
        "new_to_market_domestic_selling_target_history",
        "opportunity_domestic_selling_target_bindings",
        "new_to_market_domestic_selling_admission_history",
        "new_to_market_domestic_selling_admission_receipts",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(f"DELETE FROM {table}")
        repository._connection.rollback()
    repository.close()

    restarted = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        assert restarted.get_admission(first.admission.admission_id).admission == first.admission
        restarted._connection.execute(
            "DROP TRIGGER trg_new_to_market_domestic_selling_admission_history_no_update"
        )
        restarted._connection.execute(
            "UPDATE new_to_market_domestic_selling_admission_history "
            "SET integrity_fingerprint='bad'"
        )
        restarted._connection.commit()
        with pytest.raises(MalformedNewToMarketDomesticSellingPersistenceError):
            restarted.get_admission(first.admission.admission_id)
    finally:
        restarted.close()
        _close(resources)


def test_write_failure_rolls_back_every_new_authority_fact_and_retry_succeeds(
    tmp_path, monkeypatch
):
    path, resources, _ = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    original = repository._insert_admission

    def fail(*_):
        raise sqlite3.OperationalError("forced admission failure")

    try:
        monkeypatch.setattr(repository, "_insert_admission", fail)
        with pytest.raises(NewToMarketDomesticSellingHistoryError):
            _owner(repository)[0].execute(_command())
        for table in (
            "new_to_market_domestic_selling_target_history",
            "opportunity_domestic_selling_target_bindings",
            "new_to_market_domestic_selling_admission_history",
            "new_to_market_domestic_selling_admission_receipts",
        ):
            assert repository._connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == 0
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM opportunity_lifecycles WHERE opportunity_id='new-market-o2-1'"
        ).fetchone()[0] == 0
        monkeypatch.setattr(repository, "_insert_admission", original)
        assert _owner(repository)[0].execute(_command()).replayed is False
    finally:
        repository.close()
        _close(resources)


def test_adr_0049_then_0060_and_0060_then_0049_are_conflicts(tmp_path):
    first_path, first_resources, _ = _prepare_o1(tmp_path / "old-first")
    old_repository = SQLiteDomesticSellingOpportunityAdmissionRepository(first_path)
    new_repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(first_path)
    old_command = existing_product_command(source_opportunity_id="opportunity-v2-1")
    try:
        existing_owner(old_repository).execute(old_command)
        with pytest.raises(NewToMarketDomesticSellingCardinalityConflictError):
            _owner(new_repository)[0].execute(_command())
    finally:
        new_repository.close()
        old_repository.close()
        _close(first_resources)

    second_path, second_resources, _ = _prepare_o1(tmp_path / "new-first")
    new_repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(second_path)
    old_repository = SQLiteDomesticSellingOpportunityAdmissionRepository(second_path)
    try:
        _owner(new_repository)[0].execute(_command())
        with pytest.raises(DomesticSellingOpportunityCardinalityConflictError):
            existing_owner(old_repository).execute(old_command)
    finally:
        old_repository.close()
        new_repository.close()
        _close(second_resources)


def test_concurrent_cross_authority_attempts_create_only_one_o2(tmp_path):
    path, resources, _ = _prepare_o1(tmp_path)
    old_repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    new_repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    old_command = existing_product_command(source_opportunity_id="opportunity-v2-1")

    def existing_attempt():
        return existing_owner(old_repository).execute(old_command)

    def new_attempt():
        return _owner(new_repository)[0].execute(_command())

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(existing_attempt), pool.submit(new_attempt)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except (
                    DomesticSellingOpportunityCardinalityConflictError,
                    NewToMarketDomesticSellingCardinalityConflictError,
                ):
                    outcomes.append("conflict")
        assert sum(value != "conflict" for value in outcomes) == 1
        total = old_repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_history"
        ).fetchone()[0] + old_repository._connection.execute(
            "SELECT COUNT(*) FROM new_to_market_domestic_selling_admission_history"
        ).fetchone()[0]
        assert total == 1
    finally:
        new_repository.close()
        old_repository.close()
        _close(resources)


def test_production_api_fresh_replay_alias_validation_and_exact_response(
    tmp_path, monkeypatch
):
    path, resources, _ = _prepare_o1(tmp_path)
    _close(resources)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    app.dependency_overrides.clear()
    route = (
        "/api/v1/opportunities/opportunity-v2-1/"
        "new-to-market-domestic-selling-admissions"
    )
    with TestClient(app) as client:
        first = client.post(route, json=_api_payload())
        replay = client.post(route, json=_api_payload())
        alias = client.post(
            route, json=_api_payload(command_id="new-market-command-alias")
        )
        changed = client.post(
            route, json=_api_payload(decision_reason="changed decision")
        )
        missing = client.post(
            "/api/v1/opportunities/missing/new-to-market-domestic-selling-admissions",
            json=_api_payload(command_id="new-market-command-missing"),
        )
        invalid = _api_payload()
        invalid["product_equivalence_confirmed"] = False
        structural = client.post(route, json=invalid)

    assert first.status_code == 201, first.text
    assert replay.status_code == 200
    assert alias.status_code == 200
    assert changed.status_code == 409
    assert missing.status_code == 404
    assert structural.status_code == 422
    body = first.json()
    assert body["source_candidate_promotion"]["product_snapshot_ids"] == [
        "product-snapshot-1",
        "product-snapshot-2",
    ]
    assert body["source_product_snapshot"]["source_observation_id"] == "observation-1"
    assert body["domestic_selling_target"] == {
        "domestic_selling_target_id": body["domestic_selling_target"][
            "domestic_selling_target_id"
        ],
        "market": "KR",
        "kind": "new_to_market_domestic_selling_target",
        "schema_version": "new-to-market-domestic-selling-target-identity-v1",
    }
    assert body["bounded_kr_search"]["conclusion"] == (
        "exact_kr_identity_not_established"
    )
    assert "product_equivalence" not in body
    assert replay.json() == {**body, "replayed": True}
    assert alias.json()["admission_id"] == body["admission_id"]
    app.dependency_overrides.clear()
