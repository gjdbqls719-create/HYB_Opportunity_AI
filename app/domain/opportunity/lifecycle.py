from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text or None")
    return value.strip() or None


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


class OpportunityLifecycleStatus(StrEnum):
    DISCOVERED = "discovered"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PURCHASED = "purchased"
    LISTED = "listed"
    SOLD = "sold"


class OpportunityLifecycleAction(StrEnum):
    CREATE = "create"
    START_REVIEW = "start_review"
    APPROVE = "approve"
    REJECT = "reject"
    PURCHASE = "purchase"
    LIST = "list"
    SELL = "sell"
    RETURN_TO_REVIEW = "return_to_review"
    WITHDRAW_LISTING = "withdraw_listing"
    ARCHIVE = "archive"
    RESTORE = "restore"


class InvalidLifecycleTransitionError(ValueError):
    pass


class ArchivedLifecycleError(InvalidLifecycleTransitionError):
    pass


_ALLOWED_TRANSITIONS = {
    OpportunityLifecycleStatus.DISCOVERED: {
        OpportunityLifecycleStatus.UNDER_REVIEW,
        OpportunityLifecycleStatus.REJECTED,
    },
    OpportunityLifecycleStatus.UNDER_REVIEW: {
        OpportunityLifecycleStatus.APPROVED,
        OpportunityLifecycleStatus.REJECTED,
    },
    OpportunityLifecycleStatus.APPROVED: {
        OpportunityLifecycleStatus.PURCHASED,
        OpportunityLifecycleStatus.UNDER_REVIEW,
    },
    OpportunityLifecycleStatus.REJECTED: {
        OpportunityLifecycleStatus.UNDER_REVIEW,
    },
    OpportunityLifecycleStatus.PURCHASED: {
        OpportunityLifecycleStatus.LISTED,
    },
    OpportunityLifecycleStatus.LISTED: {
        OpportunityLifecycleStatus.SOLD,
        OpportunityLifecycleStatus.PURCHASED,
    },
    OpportunityLifecycleStatus.SOLD: set(),
}


@dataclass(frozen=True, slots=True)
class OpportunityLifecycleTransition:
    opportunity_id: str
    action: OpportunityLifecycleAction
    previous_status: OpportunityLifecycleStatus
    new_status: OpportunityLifecycleStatus
    version: int
    occurred_at: datetime
    operator_id: str
    reason: str
    note: str | None = None
    transition_id: str = field(default_factory=lambda: uuid4().hex)
    founder_decision_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "transition_id", _required_text(self.transition_id, "transition_id"))
        object.__setattr__(self, "opportunity_id", _required_text(self.opportunity_id, "opportunity_id"))
        object.__setattr__(self, "operator_id", _required_text(self.operator_id, "operator_id"))
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        object.__setattr__(self, "note", _optional_text(self.note, "note"))
        object.__setattr__(self, "founder_decision_id", _optional_text(self.founder_decision_id, "founder_decision_id"))
        _aware(self.occurred_at, "occurred_at")
        if self.version < 1:
            raise ValueError("version must be at least 1")


class OpportunityLifecycle:
    """Lifecycle aggregate with externally read-only state."""

    __slots__ = (
        "_opportunity_id",
        "_discovery_reference",
        "_status",
        "_version",
        "_created_at",
        "_updated_at",
        "_archived_at",
        "_archived_by",
        "_archive_reason",
    )

    def __init__(
        self,
        opportunity_id: str,
        discovery_reference: str,
        *,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        created = created_at or utc_now()
        updated = updated_at or created
        self._initialize(
            opportunity_id=opportunity_id,
            discovery_reference=discovery_reference,
            status=OpportunityLifecycleStatus.DISCOVERED,
            version=1,
            created_at=created,
            updated_at=updated,
            archived_at=None,
            archived_by=None,
            archive_reason=None,
        )

    @classmethod
    def _reconstitute(
        cls,
        *,
        opportunity_id: str,
        discovery_reference: str,
        status: OpportunityLifecycleStatus,
        version: int,
        created_at: datetime,
        updated_at: datetime,
        archived_at: datetime | None,
        archived_by: str | None,
        archive_reason: str | None,
    ) -> OpportunityLifecycle:
        """Repository-only reconstruction path for persisted aggregate state."""
        instance = cls.__new__(cls)
        instance._initialize(
            opportunity_id=opportunity_id,
            discovery_reference=discovery_reference,
            status=status,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
            archived_at=archived_at,
            archived_by=archived_by,
            archive_reason=archive_reason,
        )
        return instance

    def _initialize(
        self,
        *,
        opportunity_id: str,
        discovery_reference: str,
        status: OpportunityLifecycleStatus,
        version: int,
        created_at: datetime,
        updated_at: datetime,
        archived_at: datetime | None,
        archived_by: str | None,
        archive_reason: str | None,
    ) -> None:
        opportunity_id = _required_text(opportunity_id, "opportunity_id")
        discovery_reference = _required_text(discovery_reference, "discovery_reference")
        if not isinstance(status, OpportunityLifecycleStatus):
            status = OpportunityLifecycleStatus(status)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("version must be a positive integer")
        _aware(created_at, "created_at")
        _aware(updated_at, "updated_at")
        if updated_at < created_at:
            raise ValueError("updated_at cannot precede created_at")
        if archived_at is None:
            if archived_by is not None or archive_reason is not None:
                raise ValueError("archive metadata requires archived_at")
        else:
            _aware(archived_at, "archived_at")
            if archived_at < created_at:
                raise ValueError("archived_at cannot precede created_at")
            archived_by = _required_text(archived_by or "", "archived_by")
            archive_reason = _required_text(archive_reason or "", "archive_reason")
        object.__setattr__(self, "_opportunity_id", opportunity_id)
        object.__setattr__(self, "_discovery_reference", discovery_reference)
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_version", version)
        object.__setattr__(self, "_created_at", created_at)
        object.__setattr__(self, "_updated_at", updated_at)
        object.__setattr__(self, "_archived_at", archived_at)
        object.__setattr__(self, "_archived_by", archived_by)
        object.__setattr__(self, "_archive_reason", archive_reason)

    @property
    def opportunity_id(self) -> str:
        return self._opportunity_id

    @property
    def discovery_reference(self) -> str:
        return self._discovery_reference

    @property
    def status(self) -> OpportunityLifecycleStatus:
        return self._status

    @property
    def version(self) -> int:
        return self._version

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def archived_at(self) -> datetime | None:
        return self._archived_at

    @property
    def archived_by(self) -> str | None:
        return self._archived_by

    @property
    def archive_reason(self) -> str | None:
        return self._archive_reason

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def creation_transition(self, *, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._event(OpportunityLifecycleAction.CREATE, self.status, self.status, self.created_at, operator_id, reason, note)

    def start_review(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.UNDER_REVIEW, OpportunityLifecycleAction.START_REVIEW, occurred_at, operator_id, reason, note)

    def approve(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None, founder_decision_id: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.APPROVED, OpportunityLifecycleAction.APPROVE, occurred_at, operator_id, reason, note, founder_decision_id)

    def reject(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None, founder_decision_id: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.REJECTED, OpportunityLifecycleAction.REJECT, occurred_at, operator_id, reason, note, founder_decision_id)

    def purchase(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.PURCHASED, OpportunityLifecycleAction.PURCHASE, occurred_at, operator_id, reason, note)

    def list_for_sale(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.LISTED, OpportunityLifecycleAction.LIST, occurred_at, operator_id, reason, note)

    def sell(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.SOLD, OpportunityLifecycleAction.SELL, occurred_at, operator_id, reason, note)

    def return_to_review(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.UNDER_REVIEW, OpportunityLifecycleAction.RETURN_TO_REVIEW, occurred_at, operator_id, reason, note)

    def withdraw_listing(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        return self._transition(OpportunityLifecycleStatus.PURCHASED, OpportunityLifecycleAction.WITHDRAW_LISTING, occurred_at, operator_id, reason, note)

    def archive(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        if self.is_archived:
            raise ArchivedLifecycleError("lifecycle is already archived")
        self._validate_change_time(occurred_at)
        previous = self.status
        object.__setattr__(self, "_archived_at", occurred_at)
        object.__setattr__(self, "_archived_by", _required_text(operator_id, "operator_id"))
        object.__setattr__(self, "_archive_reason", _required_text(reason, "reason"))
        self._advance(occurred_at)
        return self._event(OpportunityLifecycleAction.ARCHIVE, previous, self.status, occurred_at, operator_id, reason, note)

    def restore(self, *, occurred_at: datetime, operator_id: str, reason: str, note: str | None = None) -> OpportunityLifecycleTransition:
        if not self.is_archived:
            raise ArchivedLifecycleError("lifecycle is not archived")
        self._validate_change_time(occurred_at)
        previous = self.status
        object.__setattr__(self, "_archived_at", None)
        object.__setattr__(self, "_archived_by", None)
        object.__setattr__(self, "_archive_reason", None)
        self._advance(occurred_at)
        return self._event(OpportunityLifecycleAction.RESTORE, previous, self.status, occurred_at, operator_id, reason, note)

    def _transition(self, target: OpportunityLifecycleStatus, action: OpportunityLifecycleAction, occurred_at: datetime, operator_id: str, reason: str, note: str | None, founder_decision_id: str | None = None) -> OpportunityLifecycleTransition:
        if self.is_archived:
            raise ArchivedLifecycleError("archived lifecycle must be restored before transition")
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidLifecycleTransitionError(f"transition {self.status.value} -> {target.value} is not allowed")
        self._validate_change_time(occurred_at)
        previous = self.status
        object.__setattr__(self, "_status", target)
        self._advance(occurred_at)
        return self._event(action, previous, target, occurred_at, operator_id, reason, note, founder_decision_id)

    def _validate_change_time(self, occurred_at: datetime) -> None:
        _aware(occurred_at, "occurred_at")
        if occurred_at < self.updated_at:
            raise ValueError("occurred_at cannot precede updated_at")

    def _advance(self, occurred_at: datetime) -> None:
        object.__setattr__(self, "_version", self.version + 1)
        object.__setattr__(self, "_updated_at", occurred_at)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OpportunityLifecycle):
            return NotImplemented
        return all(
            getattr(self, name) == getattr(other, name)
            for name in (
                "opportunity_id", "discovery_reference", "status", "version",
                "created_at", "updated_at", "archived_at", "archived_by",
                "archive_reason",
            )
        )

    def __repr__(self) -> str:
        return (
            "OpportunityLifecycle("
            f"opportunity_id={self.opportunity_id!r}, status={self.status!r}, "
            f"version={self.version!r}, archived_at={self.archived_at!r})"
        )

    def _event(self, action: OpportunityLifecycleAction, previous: OpportunityLifecycleStatus, target: OpportunityLifecycleStatus, occurred_at: datetime, operator_id: str, reason: str, note: str | None, founder_decision_id: str | None = None) -> OpportunityLifecycleTransition:
        return OpportunityLifecycleTransition(
            opportunity_id=self.opportunity_id,
            action=action,
            previous_status=previous,
            new_status=target,
            version=self.version,
            occurred_at=occurred_at,
            operator_id=operator_id,
            reason=reason,
            note=note,
            founder_decision_id=founder_decision_id,
        )
