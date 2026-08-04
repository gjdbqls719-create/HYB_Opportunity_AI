from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError,replace
from datetime import timedelta
import sqlite3
import pytest
from app.application.snapshot_chain_binding import *
from app.application.snapshot_chain_binding import SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION
from app.application.production_safety_runtime_adapter import ProductionSafetyRuntimeAdapter
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from app.infrastructure.economics_calculation import SQLiteEconomicsCalculationOwnerRepository
from test_candidate_issuance_foundation import Counter
from test_economics_calculation_owner_wiring import prepare as owner_prepare,boundary as economics_boundary,command as economics_command,source as economics_source,GENERATED

BOUND=GENERATED+timedelta(minutes=5)
def prepare(path):
    owner_prepare(path)
    with SQLiteEconomicsCalculationOwnerRepository(path) as repo:economics_boundary(repo).execute(economics_command())
def command(**changes):
    values={"command_id":"chain-command-1","candidate_opportunity_binding_id":"binding-1","product_snapshot_ids":("product-1","product-2"),"price_snapshot_id":"price-intelligence-1","economics_snapshot_id":"economics-owner-snapshot-1","requested_at":BOUND}
    values.update(changes);return BindOpportunitySnapshotChainCommand(**values)
def boundary(repo,*,binding_id="chain-binding-1"):return BindOpportunitySnapshotChain(repo,binding_id_generator=Counter(binding_id),bound_clock=Counter(BOUND+timedelta(seconds=1)),receipt_clock=Counter(BOUND+timedelta(seconds=2)))
def counts(repo):return tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("opportunity_snapshot_chain_binding_history","opportunity_snapshot_chain_product_members","opportunity_snapshot_chain_binding_receipts"))

def test_contract_complete_immutable_versioned_and_deterministic(tmp_path):
    prepare(tmp_path/"contract.db");c=command();assert c.fingerprint==command().fingerprint
    with pytest.raises(FrozenInstanceError):c.price_snapshot_id="x"
    with pytest.raises(SnapshotChainIncompleteError):command(product_snapshot_ids=())
    with pytest.raises(ValueError):command(product_snapshot_ids=("product-1","product-1"))
    with pytest.raises(ValueError):command(requested_at=BOUND.replace(tzinfo=None))

def test_exact_round_trip_members_receipt_restart_and_read_queries(tmp_path):
    path=tmp_path/"chain.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path);result=boundary(repo).execute(command())
    assert counts(repo)==(1,2,1) and result.binding.chain_version==1
    assert result.binding.product_snapshot_ids==("product-1","product-2")
    assert repo.get_binding("chain-binding-1")==result.binding
    assert repo.get_by_opportunity("opportunity-1")==repo.get_by_candidate("candidate-1")== (result.binding,)
    assert repo.get_receipts_by_binding(result.binding.binding_id)==(result.receipt,)
    repo.close();repo=SQLiteSnapshotChainBindingRepository(path);assert repo.get_binding(result.binding.binding_id)==result.binding;repo.close()

def test_response_loss_replay_uses_no_generator_or_clocks(tmp_path):
    path=tmp_path/"replay.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path);first=boundary(repo).execute(command());repo.close()
    class Fail:
        def __call__(self):raise AssertionError("must not be called")
    repo=SQLiteSnapshotChainBindingRepository(path);replay=BindOpportunitySnapshotChain(repo,binding_id_generator=Fail(),bound_clock=Fail(),receipt_clock=Fail()).execute(command())
    assert replay.replayed and replay.binding==first.binding and replay.receipt==first.receipt and counts(repo)==(1,2,1);repo.close()

def test_changed_same_command_conflicts_and_exact_chain_aliases(tmp_path):
    path=tmp_path/"alias.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path);first=boundary(repo).execute(command())
    with pytest.raises(SnapshotChainBindingCommandConflictError):boundary(repo).execute(replace(command(),economics_snapshot_id="other"))
    alias=boundary(repo,binding_id="must-not-win").execute(replace(command(),command_id="chain-command-2"))
    assert alias.binding==first.binding and alias.receipt.binding_id==first.binding.binding_id and counts(repo)==(1,2,2);repo.close()

def test_changed_economics_source_creates_next_chain_version(tmp_path):
    path=tmp_path/"version.db";prepare(path)
    with SQLiteEconomicsCalculationOwnerRepository(path) as economics:
        source2=replace(economics_source(),economics_calculation_command_id="economics-owner-2")
        economics_boundary(economics,snapshot_id="economics-owner-snapshot-2").execute(replace(economics_command(),command_id="economics-owner-2",source=source2))
    repo=SQLiteSnapshotChainBindingRepository(path);first=boundary(repo).execute(command());second=boundary(repo,binding_id="chain-binding-2").execute(replace(command(),command_id="chain-command-2",economics_snapshot_id="economics-owner-snapshot-2"))
    assert (first.binding.chain_version,second.binding.chain_version)==(1,2) and counts(repo)==(2,4,2);repo.close()

@pytest.mark.parametrize(
    "change,error",
    (
        ({"candidate_opportunity_binding_id":"missing"},SnapshotChainBindingNotFoundError),
        ({"product_snapshot_ids":("missing",)},SnapshotChainIncompleteError),
        ({"price_snapshot_id":"missing"},SnapshotChainIncompleteError),
        ({"economics_snapshot_id":"missing"},SnapshotChainIncompleteError),
        ({"product_snapshot_ids":("product-2","product-1")},SnapshotChainProductSourceConflictError),
    ),
)
def test_incomplete_or_inconsistent_lineage_is_rejected(tmp_path,change,error):
    path=tmp_path/"lineage.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path)
    with pytest.raises(error):boundary(repo).execute(command(**change))
    assert counts(repo)==(0,0,0) and not repo._connection.in_transaction
    repo.close()

@pytest.mark.parametrize("phase,error",(("history",SnapshotChainBindingHistoryError),("member",SnapshotChainMemberPersistenceError),("receipt",SnapshotChainReceiptPersistenceError),("commit",SnapshotChainBindingCommitError)))
def test_atomic_failure_matrix(tmp_path,phase,error):
    path=tmp_path/f"{phase}.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path)
    setattr(repo,{"history":"_insert_history","member":"_insert_members","receipt":"_insert_receipt","commit":"_commit"}[phase],lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError(phase)))
    source_before=tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("product_observation_snapshot_history","price_intelligence_snapshot_history","economics_calculation_snapshot_history"))
    with pytest.raises(error):boundary(repo).execute(command())
    assert counts(repo)==(0,0,0) and not repo._connection.in_transaction
    assert source_before==tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("product_observation_snapshot_history","price_intelligence_snapshot_history","economics_calculation_snapshot_history"));repo.close()

def test_exact_binding_builds_context_and_runtime_without_safety_execution(tmp_path):
    path=tmp_path/"safety.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path);binding=boundary(repo).execute(command()).binding
    context=repo.build_evaluation_context(binding.binding_id,"product-1")
    adapter=ProductionSafetyRuntimeAdapter(repo._owners._sources,supported_analyzer_version="price-analyzer-v1",supported_calculation_version="verified-economics-calculator-v1")
    verified=adapter.load_verified_economics_snapshot(context);runtime=adapter.reconstruct_inputs(context,verified)
    assert runtime.product.item_id==context.product_observation_snapshot.product.item_id
    assert runtime.price_intelligence.recommended_selling_price==context.price_intelligence_snapshot.recommended_selling_price
    assert runtime.economics.net_profit==context.economics_calculation_snapshot.net_profit
    with pytest.raises(SnapshotChainProductSourceConflictError):repo.build_evaluation_context(binding.binding_id,"other")
    repo.close()

def test_append_only_read_only_and_same_chain_concurrency(tmp_path):
    path=tmp_path/"race.db";prepare(path)
    def execute():
        with SQLiteSnapshotChainBindingRepository(path) as repo:return boundary(repo).execute(command())
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(lambda _:execute(),range(2)))
    assert sum(not v.replayed for v in results)==1 and results[0].binding==results[1].binding
    with SQLiteSnapshotChainBindingRepository(path) as repo:
        before=counts(repo);repo.get_binding("chain-binding-1");assert counts(repo)==before and not repo._connection.in_transaction
        for table in ("opportunity_snapshot_chain_binding_history","opportunity_snapshot_chain_product_members","opportunity_snapshot_chain_binding_receipts"):
            with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(f"DELETE FROM {table}")
            repo._connection.rollback()

def test_different_commands_same_chain_converge_to_one_binding(tmp_path):
    path=tmp_path/"alias-race.db";prepare(path)
    def execute(index):
        with SQLiteSnapshotChainBindingRepository(path) as repo:
            return boundary(repo,binding_id=f"chain-binding-{index}").execute(replace(command(),command_id=f"chain-command-{index}"))
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(execute,(1,2)))
    assert results[0].binding==results[1].binding
    with SQLiteSnapshotChainBindingRepository(path) as repo:assert counts(repo)==(1,2,2)

def test_same_command_changed_source_race_has_one_success_and_one_conflict(tmp_path):
    path=tmp_path/"conflict-race.db";prepare(path)
    with SQLiteEconomicsCalculationOwnerRepository(path) as economics:
        source2=replace(economics_source(),economics_calculation_command_id="economics-owner-2")
        economics_boundary(economics,snapshot_id="economics-owner-snapshot-2").execute(replace(economics_command(),command_id="economics-owner-2",source=source2))
    commands=(command(),replace(command(),economics_snapshot_id="economics-owner-snapshot-2"))
    def execute(value):
        try:
            with SQLiteSnapshotChainBindingRepository(path) as repo:return boundary(repo,binding_id=f"chain-{value.economics_snapshot_id}").execute(value)
        except SnapshotChainBindingCommandConflictError:return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(execute,commands))
    assert sum(value=="conflict" for value in results)==1
    with SQLiteSnapshotChainBindingRepository(path) as repo:assert counts(repo)==(1,2,1)

def test_concurrent_distinct_complete_sources_allocate_contiguous_versions(tmp_path):
    path=tmp_path/"version-race.db";prepare(path)
    with SQLiteEconomicsCalculationOwnerRepository(path) as economics:
        source2=replace(economics_source(),economics_calculation_command_id="economics-owner-2")
        economics_boundary(economics,snapshot_id="economics-owner-snapshot-2").execute(replace(economics_command(),command_id="economics-owner-2",source=source2))
    commands=(command(),replace(command(),command_id="chain-command-2",economics_snapshot_id="economics-owner-snapshot-2"))
    def execute(index_value):
        index,value=index_value
        with SQLiteSnapshotChainBindingRepository(path) as repo:return boundary(repo,binding_id=f"chain-binding-{index}").execute(value)
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(execute,enumerate(commands,1)))
    assert sorted(value.binding.chain_version for value in results)==[1,2]
    with SQLiteSnapshotChainBindingRepository(path) as repo:assert counts(repo)==(2,4,2)

def test_unsupported_and_malformed_persistence_are_explicit(tmp_path):
    path=tmp_path/"malformed.db";prepare(path);repo=SQLiteSnapshotChainBindingRepository(path);boundary(repo).execute(command())
    repo._connection.execute("DROP TRIGGER trg_opportunity_snapshot_chain_binding_history_no_update")
    repo._connection.execute("UPDATE opportunity_snapshot_chain_binding_history SET binding_schema_version='future' WHERE binding_id='chain-binding-1'")
    repo._connection.commit()
    with pytest.raises(UnsupportedSnapshotChainBindingVersionError):repo.get_binding("chain-binding-1")
    repo._connection.execute("UPDATE opportunity_snapshot_chain_binding_history SET binding_schema_version=?, payload_fingerprint='broken' WHERE binding_id='chain-binding-1'",(SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION,))
    repo._connection.commit()
    with pytest.raises(MalformedSnapshotChainBindingPersistenceError):repo.get_binding("chain-binding-1")
    repo.close()
