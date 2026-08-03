from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest

from app.application.review import (
    ApproveCandidateCommand,
    CancelReviewCommand,
    CompleteReviewCommand,
    CorrectCandidateCommand,
    CreateReviewSession,
    GetReviewSession,
    GetReviewSessionHistory,
    ListReviewSessions,
    ReviewCommandConflictError,
    ReviewCommitError,
    ReviewHistoryError,
    ReviewCandidateMembershipError,
    ReviewCandidateNotFoundError,
    ReviewOperatorMismatchError,
    ReviewPersistenceError,
    ReviewProjectionError,
    ReviewSessionHistoryError,
    ReviewSessionProjectionError,
    ReviewSessionQueryService,
    ReviewSessionVersionConflictError,
    ReviewTransitionMetadata,
    ReviewWorkflowService,
    SkipCandidateCommand,
    StartReviewCommand,
)
from app.domain.market_intelligence import (
    CandidateReviewStatus,
    CandidateSkipRecord,
    ExternalSignalDirection,
    OCRField,
)
from app.infrastructure.review import SQLiteReviewSessionRepository, SQLiteVerifiedSignalPersistence
from tests.test_review_session_persistence import NOW, candidate, identity, metadata, session


TABLES = (
    "human_verification_history",
    "human_verification_current",
    "market_observation_history",
    "market_observation_current",
    "review_session_history",
    "review_session_current",
)


def state(connection):
    return tuple(
        tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
        for table in TABLES
    )


def workflow(path):
    persistence = SQLiteVerifiedSignalPersistence(path)
    item = candidate()
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW,
        command_id="create-1",
    ))
    started = service.start_review(StartReviewCommand(
        "review-1", opened.revision, "start-1", "founder-1", NOW + timedelta(seconds=1)
    ))
    return persistence, service, started


def approve(started, *, corrected=False, command_id="review-command"):
    values = dict(
        session_id="review-1",
        candidate_id="candidate-1",
        expected_revision=started.revision,
        command_id=command_id,
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        identity=identity(),
        signal_id="signal-1",
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
    )
    return CorrectCandidateCommand(**values, corrected_value=99) if corrected else ApproveCandidateCommand(**values)


def inject_failure(connection, stage):
    if stage == "commit":
        connection.execute("CREATE TABLE commit_parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            """CREATE TABLE commit_child (id INTEGER PRIMARY KEY, parent_id INTEGER,
            FOREIGN KEY(parent_id) REFERENCES commit_parent(id) DEFERRABLE INITIALLY DEFERRED)"""
        )
        connection.execute(
            """CREATE TRIGGER fail_commit AFTER UPDATE ON review_session_current
            BEGIN INSERT INTO commit_child VALUES (1, 999); END"""
        )
        return
    table, operation = {
        "verification_history": ("human_verification_history", "INSERT"),
        "verification_current": ("human_verification_current", "INSERT"),
        "signal_history": ("market_observation_history", "INSERT"),
        "signal_current": ("market_observation_current", "INSERT"),
        "session_history": ("review_session_history", "INSERT"),
        "session_current": ("review_session_current", "UPDATE"),
    }[stage]
    connection.execute(
        f"""CREATE TRIGGER fail_{table} BEFORE {operation} ON {table}
        BEGIN SELECT RAISE(ABORT, 'forced {stage} failure'); END"""
    )


@pytest.mark.parametrize("corrected", (False, True), ids=("approve", "correct"))
@pytest.mark.parametrize(
    "stage",
    (
        "verification_history",
        "verification_current",
        "signal_history",
        "signal_current",
        "session_history",
        "session_current",
        "commit",
    ),
)
def test_full_verified_review_atomic_failure_matrix(tmp_path, corrected, stage) -> None:
    persistence, service, started = workflow(tmp_path / f"{stage}-{corrected}.db")
    before = state(persistence._connection)
    inject_failure(persistence._connection, stage)
    expected_error = (
        ReviewHistoryError
        if stage.endswith("history")
        else ReviewProjectionError
        if stage.endswith("current")
        else ReviewCommitError
    )
    with pytest.raises(expected_error):
        command = approve(started, corrected=corrected)
        (service.correct_candidate(command) if corrected else service.approve_candidate(command))
    assert state(persistence._connection) == before
    assert persistence.sessions.get("review-1") == started
    assert persistence._connection.in_transaction is False


@pytest.mark.parametrize("stage,error", (("history", ReviewSessionHistoryError), ("current", ReviewSessionProjectionError)))
def test_non_ledger_transition_failure_preserves_prior_state(tmp_path, stage, error) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / f"{stage}.db")
    opened = repository.create(session(), metadata())
    started = opened.start(operator_id="founder-1", started_at=NOW)
    table = "review_session_history" if stage == "history" else "review_session_current"
    operation = "INSERT" if stage == "history" else "UPDATE"
    repository._connection.execute(
        f"""CREATE TRIGGER fail_transition BEFORE {operation} ON {table}
        BEGIN SELECT RAISE(ABORT, 'forced failure'); END"""
    )
    before = state_for_review(repository._connection)
    with pytest.raises(error):
        repository.save_transition(opened, started, metadata("start", "start-fp", "start"))
    assert state_for_review(repository._connection) == before
    assert repository._connection.in_transaction is False


def state_for_review(connection):
    return tuple(
        tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
        for table in ("review_session_history", "review_session_current")
    )


@pytest.mark.parametrize(
    "stage,error",
    (
        ("history", ReviewSessionHistoryError),
        ("current", ReviewSessionProjectionError),
        ("commit", ReviewPersistenceError),
    ),
)
def test_create_failure_matrix_has_no_partial_rows(tmp_path, stage, error) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / f"create-{stage}.db")
    if stage == "history":
        repository._connection.execute(
            """CREATE TRIGGER fail_create BEFORE INSERT ON review_session_history
            BEGIN SELECT RAISE(ABORT, 'history'); END"""
        )
    elif stage == "current":
        repository._connection.execute(
            """CREATE TRIGGER fail_create BEFORE INSERT ON review_session_current
            BEGIN SELECT RAISE(ABORT, 'current'); END"""
        )
    else:
        repository._connection.execute("CREATE TABLE commit_parent (id INTEGER PRIMARY KEY)")
        repository._connection.execute(
            """CREATE TABLE commit_child (id INTEGER PRIMARY KEY, parent_id INTEGER,
            FOREIGN KEY(parent_id) REFERENCES commit_parent(id) DEFERRABLE INITIALLY DEFERRED)"""
        )
        repository._connection.execute(
            """CREATE TRIGGER fail_create AFTER INSERT ON review_session_current
            BEGIN INSERT INTO commit_child VALUES (1, 999); END"""
        )
    with pytest.raises(error):
        repository.create(session(), metadata())
    assert state_for_review(repository._connection) == ((), ())
    assert repository._connection.in_transaction is False


def test_non_ledger_transition_commit_failure_preserves_prior_state(tmp_path) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / "transition-commit.db")
    opened = repository.create(session(), metadata())
    started = opened.start(operator_id="founder-1", started_at=NOW)
    repository._connection.execute("CREATE TABLE commit_parent (id INTEGER PRIMARY KEY)")
    repository._connection.execute(
        """CREATE TABLE commit_child (id INTEGER PRIMARY KEY, parent_id INTEGER,
        FOREIGN KEY(parent_id) REFERENCES commit_parent(id) DEFERRABLE INITIALLY DEFERRED)"""
    )
    repository._connection.execute(
        """CREATE TRIGGER fail_transition AFTER UPDATE ON review_session_current
        BEGIN INSERT INTO commit_child VALUES (1, 999); END"""
    )
    before = state_for_review(repository._connection)
    with pytest.raises(ReviewPersistenceError):
        repository.save_transition(opened, started, metadata("start", "start-fp", "start"))
    assert state_for_review(repository._connection) == before
    assert repository._connection.in_transaction is False


@pytest.mark.parametrize("transition", ("start", "skip", "complete", "cancel"))
@pytest.mark.parametrize("stage", ("history", "current", "commit"))
def test_each_non_ledger_transition_failure_matrix(tmp_path, transition, stage) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / f"{transition}-{stage}.db")
    opened = repository.create(session(), metadata())
    if transition == "cancel":
        previous = opened
        next_session = opened.cancel(operator_id="founder-1", cancelled_at=NOW)
    else:
        started = opened.start(operator_id="founder-1", started_at=NOW)
        if transition == "start":
            previous, next_session = opened, started
        else:
            repository.save_transition(
                opened, started, metadata("prerequisite-start", "prerequisite-start", "start")
            )
            skipped = started.mark_candidate(
                "candidate-1",
                CandidateReviewStatus.SKIPPED,
                operator_id="founder-1",
                skip_record=CandidateSkipRecord(
                    "candidate-1", "founder-1", "skip", NOW
                ),
            )
            if transition == "skip":
                previous, next_session = started, skipped
            else:
                repository.save_transition(
                    started, skipped, metadata("prerequisite-skip", "prerequisite-skip", "skip")
                )
                previous = skipped
                next_session = skipped.complete(operator_id="founder-1", completed_at=NOW)
    if stage == "history":
        repository._connection.execute(
            """CREATE TRIGGER fail_matrix BEFORE INSERT ON review_session_history
            BEGIN SELECT RAISE(ABORT, 'history'); END"""
        )
    elif stage == "current":
        repository._connection.execute(
            """CREATE TRIGGER fail_matrix BEFORE UPDATE ON review_session_current
            BEGIN SELECT RAISE(ABORT, 'current'); END"""
        )
    else:
        repository._connection.execute("CREATE TABLE commit_parent (id INTEGER PRIMARY KEY)")
        repository._connection.execute(
            """CREATE TABLE commit_child (id INTEGER PRIMARY KEY, parent_id INTEGER,
            FOREIGN KEY(parent_id) REFERENCES commit_parent(id) DEFERRABLE INITIALLY DEFERRED)"""
        )
        repository._connection.execute(
            """CREATE TRIGGER fail_matrix AFTER UPDATE ON review_session_current
            BEGIN INSERT INTO commit_child VALUES (1, 999); END"""
        )
    before = state_for_review(repository._connection)
    with pytest.raises(ReviewPersistenceError):
        repository.save_transition(
            previous,
            next_session,
            metadata(f"{transition}-{stage}", f"{transition}-{stage}", transition),
        )
    assert state_for_review(repository._connection) == before
    assert repository.get("review-1") == previous
    assert repository._connection.in_transaction is False


def test_id_commands_replay_every_transition_without_duplicate_facts(tmp_path) -> None:
    persistence, service, started = workflow(tmp_path / "replay.db")
    assert service.start_review(StartReviewCommand(
        "review-1", 1, "start-1", "founder-1", NOW + timedelta(seconds=1)
    )) == started
    with pytest.raises(ReviewCommandConflictError):
        service.start_review(StartReviewCommand(
            "review-1", 1, "start-1", "founder-1", NOW + timedelta(seconds=2)
        ))
    skipped_command = SkipCandidateCommand(
        "review-1", "candidate-1", 2, "skip-1", "founder-1", "irrelevant", NOW + timedelta(minutes=1)
    )
    skipped = service.skip_candidate(skipped_command)
    assert service.skip_candidate(skipped_command) == skipped
    with pytest.raises(ReviewCommandConflictError):
        service.skip_candidate(replace(skipped_command, reason="changed"))
    complete_command = CompleteReviewCommand(
        "review-1", 3, "complete-1", "founder-1", NOW + timedelta(minutes=2)
    )
    completed = service.complete_review(complete_command)
    assert service.complete_review(complete_command) == completed
    with pytest.raises(ReviewCommandConflictError):
        service.complete_review(replace(
            complete_command, completed_at=NOW + timedelta(minutes=3)
        ))
    assert len(persistence.sessions.get_history("review-1")) == 4

    cancel_persistence = SQLiteVerifiedSignalPersistence(tmp_path / "cancel.db")
    cancel_service = ReviewWorkflowService(cancel_persistence.ledger, persistence=cancel_persistence)
    opened = cancel_service.create_session(CreateReviewSession(
        "cancel-1", "artifact-1", ("candidate-1",), "founder-1", NOW, command_id="create-cancel"
    ))
    cancel_command = CancelReviewCommand("cancel-1", 1, "cancel-command", "founder-1", NOW)
    cancelled = cancel_service.cancel_review(cancel_command)
    assert cancel_service.cancel_review(cancel_command) == cancelled
    with pytest.raises(ReviewCommandConflictError):
        cancel_service.cancel_review(replace(
            cancel_command, cancelled_at=NOW + timedelta(minutes=1)
        ))
    assert len(cancel_persistence.sessions.get_history("cancel-1")) == 2


@pytest.mark.parametrize("corrected", (False, True), ids=("approve", "correct"))
def test_verified_command_replay_returns_exact_existing_facts(tmp_path, corrected) -> None:
    persistence, service, started = workflow(tmp_path / f"replay-{corrected}.db")
    command = approve(started, corrected=corrected, command_id="verified-command")
    first = service.correct_candidate(command) if corrected else service.approve_candidate(command)
    replay = service.correct_candidate(command) if corrected else service.approve_candidate(command)
    assert replay == first
    assert replay.verification.verification_id == "verification-1"
    assert replay.signal.signal_id == "signal-1"
    assert len(persistence.ledger.get_verification_history("candidate-1")) == 1
    assert len(persistence.sessions.get_history("review-1")) == 3
    with pytest.raises(ReviewCommandConflictError):
        changed = replace(command, comment="changed payload")
        (service.correct_candidate(changed) if corrected else service.approve_candidate(changed))


def test_command_conflict_stale_revision_and_operator_taxonomy(tmp_path) -> None:
    persistence, service, started = workflow(tmp_path / "conflicts.db")
    original = SkipCandidateCommand(
        "review-1", "candidate-1", 2, "skip-1", "founder-1", "one", NOW + timedelta(minutes=1)
    )
    service.skip_candidate(original)
    with pytest.raises(ReviewCommandConflictError):
        service.skip_candidate(replace(original, reason="changed"))
    with pytest.raises(ReviewSessionVersionConflictError):
        service.skip_candidate(replace(original, command_id="skip-2"))

    other = SQLiteVerifiedSignalPersistence(tmp_path / "operator.db")
    other.ledger.save_candidate(candidate())
    other_service = ReviewWorkflowService(other.ledger, persistence=other)
    opened = other_service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    with pytest.raises(ReviewOperatorMismatchError):
        other_service.start_review(StartReviewCommand(
            "review-1", opened.revision, "bad-operator", "other", NOW
        ))


def test_id_command_loads_authoritative_candidate_and_membership(tmp_path) -> None:
    persistence, service, started = workflow(tmp_path / "authoritative.db")
    with pytest.raises(ReviewCandidateNotFoundError):
        service.skip_candidate(SkipCandidateCommand(
            "review-1", "missing", started.revision, "missing-1",
            "founder-1", "missing", NOW,
        ))
    extra = replace(
        candidate(),
        candidate_id="candidate-2",
        field_name=OCRField.RATING,
    )
    persistence.ledger.save_candidate(extra)
    before = state(persistence._connection)
    with pytest.raises(ReviewCandidateMembershipError):
        service.skip_candidate(SkipCandidateCommand(
            "review-1", "candidate-2", started.revision, "membership-1",
            "founder-1", "not a member", NOW,
        ))
    assert state(persistence._connection) == before


def test_current_projection_rebuild_and_read_only_queries(tmp_path) -> None:
    persistence, service, started = workflow(tmp_path / "rebuild.db")
    skipped = service.skip_candidate(SkipCandidateCommand(
        "review-1", "candidate-1", 2, "skip-1", "founder-1", "skip", NOW + timedelta(minutes=1)
    )).session
    before = state(persistence._connection)
    queries = ReviewSessionQueryService(persistence.sessions)
    expected = (
        queries.get(GetReviewSession("review-1")),
        queries.list(ListReviewSessions()),
        queries.history(GetReviewSessionHistory("review-1")),
    )
    assert expected == (
        queries.get(GetReviewSession("review-1")),
        queries.list(ListReviewSessions()),
        queries.history(GetReviewSessionHistory("review-1")),
    )
    assert state(persistence._connection) == before
    assert persistence._connection.in_transaction is False

    persistence._connection.execute("DELETE FROM review_session_current")
    persistence._connection.commit()
    rebuilt = persistence.sessions.rebuild_current()
    assert rebuilt == (skipped,)
    assert persistence.sessions.get("review-1") == skipped


@pytest.mark.parametrize("terminal", ("skip_complete", "cancel"))
def test_terminal_and_skip_restart_round_trip(tmp_path, terminal) -> None:
    path = tmp_path / f"restart-{terminal}.db"
    persistence = SQLiteVerifiedSignalPersistence(path)
    persistence.ledger.save_candidate(candidate())
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    if terminal == "cancel":
        expected = service.cancel_review(CancelReviewCommand(
            "review-1", 1, "cancel-1", "founder-1", NOW + timedelta(minutes=1)
        ))
    else:
        started = service.start_review(StartReviewCommand(
            "review-1", 1, "start-1", "founder-1", NOW
        ))
        skipped = service.skip_candidate(SkipCandidateCommand(
            "review-1", "candidate-1", started.revision, "skip-1", "founder-1", "skip", NOW
        )).session
        expected = service.complete_review(CompleteReviewCommand(
            "review-1", skipped.revision, "complete-1", "founder-1", NOW + timedelta(minutes=1)
        ))
    persistence.close()
    restarted = SQLiteReviewSessionRepository(path)
    assert restarted.get("review-1") == expected


def test_real_multi_connection_start_race(tmp_path) -> None:
    path = tmp_path / "race.db"
    persistence = SQLiteVerifiedSignalPersistence(path)
    persistence.ledger.save_candidate(candidate())
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    persistence.close()
    barrier = Barrier(2)

    def attempt(command_id):
        local = SQLiteVerifiedSignalPersistence(path)
        local_service = ReviewWorkflowService(local.ledger, persistence=local)
        command = StartReviewCommand("review-1", 1, command_id, "founder-1", NOW)
        barrier.wait()
        try:
            return local_service.start_review(command)
        except Exception as error:
            return error
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(attempt, ("start-a", "start-b")))
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ReviewSessionVersionConflictError) for result in results) == 1
    repository = SQLiteReviewSessionRepository(path)
    assert repository.get("review-1").revision == 2
    assert [entry.session.revision for entry in repository.get_history("review-1")] == [1, 2]


@pytest.mark.parametrize(
    "left,right",
    (("approve", "approve"), ("approve", "correct"), ("approve", "skip")),
)
def test_real_multi_connection_candidate_action_races(tmp_path, left, right) -> None:
    path = tmp_path / f"race-{left}-{right}.db"
    persistence, _, started = workflow(path)
    persistence.close()
    barrier = Barrier(2)

    def attempt(action, suffix):
        local = SQLiteVerifiedSignalPersistence(path)
        service = ReviewWorkflowService(local.ledger, persistence=local)
        if action == "skip":
            command = SkipCandidateCommand(
                "review-1", "candidate-1", started.revision, f"skip-{suffix}",
                "founder-1", "skip", NOW + timedelta(minutes=1),
            )
        else:
            values = dict(
                session_id="review-1",
                candidate_id="candidate-1",
                expected_revision=started.revision,
                command_id=f"{action}-{suffix}",
                verification_id=f"verification-{suffix}",
                operator_id="founder-1",
                verified_at=NOW + timedelta(minutes=1),
                identity=identity(),
                signal_id=f"signal-{suffix}",
                signal_name="search volume",
                signal_direction=ExternalSignalDirection.POSITIVE,
            )
            command = (
                CorrectCandidateCommand(**values, corrected_value=101)
                if action == "correct"
                else ApproveCandidateCommand(**values)
            )
        barrier.wait()
        try:
            if action == "approve":
                return service.approve_candidate(command)
            if action == "correct":
                return service.correct_candidate(command)
            return service.skip_candidate(command)
        except Exception as error:
            return error
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(attempt, left, "a"),
            executor.submit(attempt, right, "b"),
        )
        results = tuple(future.result() for future in futures)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    repository = SQLiteReviewSessionRepository(path)
    current = repository.get("review-1")
    assert current.revision == 3
    assert [entry.session.revision for entry in repository.get_history("review-1")] == [1, 2, 3]
    check = SQLiteVerifiedSignalPersistence(path)
    verification_count = len(check.ledger.get_verification_history("candidate-1"))
    assert verification_count == (0 if current.candidate_statuses[0][1] is CandidateReviewStatus.SKIPPED else 1)
    check.close()


def test_real_multi_connection_cancel_vs_start(tmp_path) -> None:
    path = tmp_path / "cancel-start.db"
    persistence = SQLiteVerifiedSignalPersistence(path)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    persistence.close()
    barrier = Barrier(2)

    def attempt(action):
        local = SQLiteVerifiedSignalPersistence(path)
        service = ReviewWorkflowService(local.ledger, persistence=local)
        command = (
            StartReviewCommand("review-1", 1, "start-1", "founder-1", NOW)
            if action == "start"
            else CancelReviewCommand("review-1", 1, "cancel-1", "founder-1", NOW)
        )
        barrier.wait()
        try:
            return service.start_review(command) if action == "start" else service.cancel_review(command)
        except Exception as error:
            return error
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(attempt, ("start", "cancel")))
    assert sum(not isinstance(result, Exception) for result in results) == 1
    repository = SQLiteReviewSessionRepository(path)
    assert repository.get("review-1").revision == 2
    assert [entry.session.revision for entry in repository.get_history("review-1")] == [1, 2]


def test_real_multi_connection_complete_vs_approve(tmp_path) -> None:
    path = tmp_path / "complete-approve.db"
    persistence, _, started = workflow(path)
    persistence.close()
    barrier = Barrier(2)

    def attempt(action):
        local = SQLiteVerifiedSignalPersistence(path)
        service = ReviewWorkflowService(local.ledger, persistence=local)
        command = (
            CompleteReviewCommand(
                "review-1", started.revision, "complete-1", "founder-1", NOW + timedelta(minutes=2)
            )
            if action == "complete"
            else approve(started, command_id="approve-1")
        )
        barrier.wait()
        try:
            return (
                service.complete_review(command)
                if action == "complete"
                else service.approve_candidate(command)
            )
        except Exception as error:
            return error
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(attempt, ("complete", "approve")))
    assert sum(not isinstance(result, Exception) for result in results) == 1
    repository = SQLiteReviewSessionRepository(path)
    assert repository.get("review-1").revision == 3
    assert dict(repository.get("review-1").candidate_statuses)["candidate-1"] is CandidateReviewStatus.APPROVED
