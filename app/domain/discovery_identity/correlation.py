"""Stable command and group-correlation contracts for discovery replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.product_observation import CollectorProvenance, ObservedProductSnapshot


DISCOVERY_COMMAND_SCHEMA_VERSION = "discovery-command-v1"
COLLECTOR_OBSERVATION_SCHEMA_VERSION = "collector-observation-v1"
CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION = (
    "collector-observation-v2"
)
CANDIDATE_HANDOFF_POLICY_NAME = "discovery-candidate-handoff"
CANDIDATE_HANDOFF_POLICY_VERSION = "1.0.0"
FINALIZED_PRODUCT_GROUP_SCHEMA_VERSION = "finalized-product-group-v1"
DISCOVERY_EXECUTION_RESULT_SCHEMA_VERSION = "discovery-execution-result-v1"
CANDIDATE_ISSUANCE_REPLAY_SCHEMA_VERSION = "candidate-issuance-replay-v1"


class DiscoveryCorrelationError(ValueError):
    pass


class MalformedDiscoveryCommandError(DiscoveryCorrelationError):
    pass


class UnsupportedDiscoveryCommandVersionError(DiscoveryCorrelationError):
    pass


class MalformedCollectorObservationError(DiscoveryCorrelationError):
    pass


class DiscoveryObservationIdentityConflictError(DiscoveryCorrelationError):
    pass


class MalformedFinalizedProductGroupError(DiscoveryCorrelationError):
    pass


class DiscoveryGroupMembershipConflictError(DiscoveryCorrelationError):
    pass


class DiscoveryCommandPayloadConflictError(DiscoveryCorrelationError):
    pass


class DiscoveryMarketIdentityResolutionError(DiscoveryCorrelationError):
    pass


def _required(value: str, name: str, error_type: type[Exception] = ValueError) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str, error_type: type[Exception]) -> datetime:
    if not isinstance(value, datetime):
        raise error_type(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error_type(f"{name} must be timezone-aware")
    return value


def _decimal(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise MalformedDiscoveryCommandError(f"{name} must be Decimal")
    if not value.is_finite():
        raise MalformedDiscoveryCommandError(f"{name} must be finite")
    return value


def _reference_items(
    values: tuple[tuple[str, str], ...], name: str
) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, tuple):
        raise MalformedDiscoveryCommandError(f"{name} must be a tuple")
    normalized: list[tuple[str, str]] = []
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise MalformedDiscoveryCommandError(
                f"{name} must contain name/reference tuples"
            )
        normalized.append(
            (
                _required(item[0], f"{name} name", MalformedDiscoveryCommandError),
                _required(item[1], f"{name} reference", MalformedDiscoveryCommandError),
            )
        )
    if len({key for key, _ in normalized}) != len(normalized):
        raise MalformedDiscoveryCommandError(
            f"{name} must be uniquely keyed"
        )
    return tuple(sorted(normalized))


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return {"kind": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {
            "kind": "datetime",
            "value": value.astimezone(timezone.utc).isoformat(),
        }
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        _json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identity_payload(identity: MarketObservationIdentity) -> dict[str, object]:
    return {
        "scope": identity.scope.value,
        "market": identity.market,
        "marketplace": identity.marketplace,
        "canonical_product_id": identity.canonical_product_id,
        "marketplace_item_id": identity.marketplace_item_id,
        "normalized_query": identity.normalized_query,
        "category": identity.category,
        "variant_identity": identity.variant_identity,
        "condition": identity.condition,
        "window_started_at": identity.window_started_at,
        "window_ended_at": identity.window_ended_at,
    }


def _candidate_market_identity(identity: MarketObservationIdentity) -> None:
    if not isinstance(identity, MarketObservationIdentity):
        raise DiscoveryMarketIdentityResolutionError(
            "candidate market identity must be MarketObservationIdentity"
        )
    if identity.scope not in {
        MarketObservationScope.LISTING,
        MarketObservationScope.CANONICAL_PRODUCT,
    }:
        raise DiscoveryMarketIdentityResolutionError(
            "candidate market identity must use listing or canonical_product scope"
        )


@dataclass(frozen=True, slots=True)
class DiscoveryCommandParameters:
    query: str
    selling_price_multiplier: Decimal
    shipping_cost: Decimal | None
    marketplace_fee_rate: Decimal
    payment_fee_rate: Decimal
    fixed_fee: Decimal | None
    marketplace_fee_known: bool
    payment_fee_known: bool
    fixed_fee_known: bool
    tax_rate: Decimal
    other_cost: Decimal
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    estimated_monthly_sales: int
    competitor_count: int
    risk_level: str
    limit: int
    match_threshold: Decimal
    target_currency: str | None = None
    policy_references: tuple[tuple[str, str], ...] = ()
    source_references: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _required(self.query, "query", MalformedDiscoveryCommandError))
        for name in (
            "selling_price_multiplier", "marketplace_fee_rate", "payment_fee_rate",
            "tax_rate", "other_cost", "minimum_net_profit", "minimum_roi",
            "match_threshold",
        ):
            _decimal(getattr(self, name), name)
        for name in ("shipping_cost", "fixed_fee"):
            value = getattr(self, name)
            if value is not None:
                _decimal(value, name)
        if self.selling_price_multiplier <= 0:
            raise MalformedDiscoveryCommandError(
                "selling_price_multiplier must be positive"
            )
        if not Decimal("0") <= self.match_threshold <= Decimal("100"):
            raise MalformedDiscoveryCommandError(
                "match_threshold must be between 0 and 100"
            )
        for name in ("estimated_monthly_sales", "competitor_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MalformedDiscoveryCommandError(
                    f"{name} must be a non-negative integer"
                )
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1:
            raise MalformedDiscoveryCommandError("limit must be a positive integer")
        for name in (
            "marketplace_fee_known", "payment_fee_known", "fixed_fee_known"
        ):
            if not isinstance(getattr(self, name), bool):
                raise MalformedDiscoveryCommandError(f"{name} must be bool")
        object.__setattr__(self, "risk_level", _required(self.risk_level, "risk_level", MalformedDiscoveryCommandError))
        if self.target_currency is not None:
            object.__setattr__(
                self, "target_currency", _required(self.target_currency, "target_currency", MalformedDiscoveryCommandError).upper()
            )
        object.__setattr__(self, "policy_references", _reference_items(self.policy_references, "policy_references"))
        object.__setattr__(self, "source_references", _reference_items(self.source_references, "source_references"))

    def canonical_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiscoveryCommand:
    command_id: str
    discovery_execution_id: str
    parameters: DiscoveryCommandParameters
    requested_at: datetime
    schema_version: str = DISCOVERY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "discovery_execution_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name, MalformedDiscoveryCommandError))
        if not isinstance(self.parameters, DiscoveryCommandParameters):
            raise MalformedDiscoveryCommandError(
                "parameters must be DiscoveryCommandParameters"
            )
        _aware(self.requested_at, "requested_at", MalformedDiscoveryCommandError)
        if self.schema_version != DISCOVERY_COMMAND_SCHEMA_VERSION:
            raise UnsupportedDiscoveryCommandVersionError(
                f"unsupported discovery command version: {self.schema_version}"
            )

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "discovery_execution_id": self.discovery_execution_id,
                "parameters": self.parameters.canonical_payload(),
                "requested_at": self.requested_at,
                "schema_version": self.schema_version,
            }
        )


@dataclass(frozen=True, slots=True)
class CollectedProductObservation:
    observation_id: str
    discovery_execution_id: str
    source_marketplace: str
    source_item_id: str
    product: ObservedProductSnapshot
    collector_provenance: CollectorProvenance
    observed_at: datetime
    candidate_market_identity: MarketObservationIdentity | None = None
    candidate_discovery_reference: str | None = None
    candidate_handoff_policy_name: str | None = None
    candidate_handoff_policy_version: str | None = None
    schema_version: str = COLLECTOR_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "observation_id", "discovery_execution_id", "source_marketplace",
            "source_item_id",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name, MalformedCollectorObservationError))
        if not isinstance(self.product, ObservedProductSnapshot):
            raise MalformedCollectorObservationError(
                "product must be ObservedProductSnapshot"
            )
        if not isinstance(self.collector_provenance, CollectorProvenance):
            raise MalformedCollectorObservationError(
                "collector_provenance must be CollectorProvenance"
            )
        if (
            self.product.marketplace != self.source_marketplace
            or self.product.item_id != self.source_item_id
        ):
            raise DiscoveryObservationIdentityConflictError(
                "source identity must match the observed Product"
            )
        _aware(self.observed_at, "observed_at", MalformedCollectorObservationError)
        if self.candidate_market_identity is not None:
            _candidate_market_identity(self.candidate_market_identity)
            if self.candidate_market_identity.marketplace != self.source_marketplace:
                raise DiscoveryObservationIdentityConflictError(
                    "Market identity marketplace must match source marketplace"
                )
            if (
                self.candidate_market_identity.scope is MarketObservationScope.LISTING
                and self.candidate_market_identity.marketplace_item_id
                != self.source_item_id
            ):
                raise DiscoveryObservationIdentityConflictError(
                    "listing Market identity must match source item"
                )
        if self.schema_version == COLLECTOR_OBSERVATION_SCHEMA_VERSION:
            if any(
                value is not None
                for value in (
                    self.candidate_discovery_reference,
                    self.candidate_handoff_policy_name,
                    self.candidate_handoff_policy_version,
                )
            ):
                raise MalformedCollectorObservationError(
                    "legacy observations cannot contain Candidate handoff fields"
                )
            return
        if self.schema_version != CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION:
            raise MalformedCollectorObservationError(
                f"unsupported collector observation version: {self.schema_version}"
            )
        if self.candidate_market_identity is None:
            raise MalformedCollectorObservationError(
                "Candidate handoff Market identity is required"
            )
        object.__setattr__(
            self,
            "candidate_discovery_reference",
            _required(
                self.candidate_discovery_reference,
                "candidate_discovery_reference",
                MalformedCollectorObservationError,
            ),
        )
        object.__setattr__(
            self,
            "candidate_handoff_policy_name",
            _required(
                self.candidate_handoff_policy_name,
                "candidate_handoff_policy_name",
                MalformedCollectorObservationError,
            ),
        )
        object.__setattr__(
            self,
            "candidate_handoff_policy_version",
            _required(
                self.candidate_handoff_policy_version,
                "candidate_handoff_policy_version",
                MalformedCollectorObservationError,
            ),
        )
        if (
            self.candidate_handoff_policy_name != CANDIDATE_HANDOFF_POLICY_NAME
            or self.candidate_handoff_policy_version
            != CANDIDATE_HANDOFF_POLICY_VERSION
        ):
            raise MalformedCollectorObservationError(
                "unsupported Candidate handoff policy"
            )
        identity = self.candidate_market_identity
        if (
            identity.scope is not MarketObservationScope.LISTING
            or identity.market != "US"
            or identity.marketplace != "ebay"
            or identity.canonical_product_id is not None
            or identity.normalized_query is not None
            or identity.category is not None
            or identity.variant_identity is not None
            or identity.window_started_at != self.observed_at
            or identity.window_ended_at != self.observed_at
            or self.collector_provenance.collector_name != "ebay"
        ):
            raise DiscoveryObservationIdentityConflictError(
                "Candidate handoff identity conflicts with eBay US policy"
            )

    @property
    def is_candidate_eligible(self) -> bool:
        return (
            self.schema_version
            == CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION
        )


@dataclass(frozen=True, slots=True)
class FinalizedProductGroup:
    finalized_group_id: str
    discovery_execution_id: str
    observation_ids: tuple[str, ...]
    grouping_policy_version: str
    representative_observation_id: str
    finalized_at: datetime
    schema_version: str = FINALIZED_PRODUCT_GROUP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "finalized_group_id", "discovery_execution_id", "grouping_policy_version",
            "representative_observation_id",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name, MalformedFinalizedProductGroupError))
        if not isinstance(self.observation_ids, tuple) or not self.observation_ids:
            raise MalformedFinalizedProductGroupError(
                "observation_ids must be a non-empty tuple"
            )
        normalized = tuple(
            _required(value, "observation_id", MalformedFinalizedProductGroupError)
            for value in self.observation_ids
        )
        if len(set(normalized)) != len(normalized):
            raise DiscoveryGroupMembershipConflictError(
                "observation_ids must be unique"
            )
        if self.representative_observation_id not in normalized:
            raise DiscoveryGroupMembershipConflictError(
                "representative observation must belong to the group"
            )
        object.__setattr__(self, "observation_ids", normalized)
        _aware(self.finalized_at, "finalized_at", MalformedFinalizedProductGroupError)
        if self.schema_version != FINALIZED_PRODUCT_GROUP_SCHEMA_VERSION:
            raise MalformedFinalizedProductGroupError(
                f"unsupported finalized group version: {self.schema_version}"
            )

    @property
    def membership_fingerprint(self) -> str:
        return _fingerprint(
            {
                "discovery_execution_id": self.discovery_execution_id,
                "observation_ids": self.observation_ids,
                "grouping_policy_version": self.grouping_policy_version,
                "representative_observation_id": self.representative_observation_id,
                "schema_version": self.schema_version,
            }
        )


@dataclass(frozen=True, slots=True)
class DiscoveryExecutionResult:
    command_id: str
    discovery_execution_id: str
    finalized_group_ids: tuple[str, ...]
    completed_at: datetime
    schema_version: str = DISCOVERY_EXECUTION_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "discovery_execution_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name, DiscoveryCommandPayloadConflictError))
        if not isinstance(self.finalized_group_ids, tuple):
            raise DiscoveryCommandPayloadConflictError(
                "finalized_group_ids must be a tuple"
            )
        normalized = tuple(
            _required(value, "finalized_group_id", DiscoveryCommandPayloadConflictError)
            for value in self.finalized_group_ids
        )
        if len(set(normalized)) != len(normalized):
            raise DiscoveryCommandPayloadConflictError(
                "finalized_group_ids must be unique"
            )
        object.__setattr__(self, "finalized_group_ids", normalized)
        _aware(self.completed_at, "completed_at", DiscoveryCommandPayloadConflictError)
        if self.schema_version != DISCOVERY_EXECUTION_RESULT_SCHEMA_VERSION:
            raise DiscoveryCommandPayloadConflictError(
                f"unsupported execution result version: {self.schema_version}"
            )

    @property
    def is_zero_result(self) -> bool:
        return not self.finalized_group_ids

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "command_id": self.command_id,
                "discovery_execution_id": self.discovery_execution_id,
                "finalized_group_ids": self.finalized_group_ids,
                "completed_at": self.completed_at,
                "schema_version": self.schema_version,
            }
        )


@dataclass(frozen=True, slots=True)
class CandidateIssuanceReplayKey:
    command_id: str
    finalized_group_id: str
    command_fingerprint: str
    membership_fingerprint: str
    market_observation_identity: MarketObservationIdentity
    issuance_schema_version: str = CANDIDATE_ISSUANCE_REPLAY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id", "finalized_group_id", "command_fingerprint",
            "membership_fingerprint", "issuance_schema_version",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name, DiscoveryCommandPayloadConflictError))
        _candidate_market_identity(self.market_observation_identity)
        if self.issuance_schema_version != CANDIDATE_ISSUANCE_REPLAY_SCHEMA_VERSION:
            raise DiscoveryCommandPayloadConflictError(
                "unsupported candidate issuance replay version"
            )

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "command_fingerprint": self.command_fingerprint,
                "membership_fingerprint": self.membership_fingerprint,
                "market_observation_identity": _identity_payload(
                    self.market_observation_identity
                ),
                "issuance_schema_version": self.issuance_schema_version,
            }
        )


__all__ = [name for name in globals() if name.startswith("Discovery") or name in {
    "CANDIDATE_ISSUANCE_REPLAY_SCHEMA_VERSION",
    "COLLECTOR_OBSERVATION_SCHEMA_VERSION",
    "DISCOVERY_COMMAND_SCHEMA_VERSION",
    "DISCOVERY_EXECUTION_RESULT_SCHEMA_VERSION",
    "FINALIZED_PRODUCT_GROUP_SCHEMA_VERSION",
    "CandidateIssuanceReplayKey",
    "CollectedProductObservation",
    "FinalizedProductGroup",
    "MalformedCollectorObservationError",
    "MalformedFinalizedProductGroupError",
    "MalformedDiscoveryCommandError",
    "UnsupportedDiscoveryCommandVersionError",
}]
