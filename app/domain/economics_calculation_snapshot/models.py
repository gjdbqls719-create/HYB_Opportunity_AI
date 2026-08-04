"""Immutable snapshot contract for an authoritative EconomicsCalculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite

from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.opportunity import MoneyInput
from app.domain.economics_calculation_snapshot.analysis import EconomicsAnalysisSnapshot


ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION = "economics-calculation-snapshot-v3"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _decimal(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def _immutable_context_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, tuple):
        return all(_immutable_context_value(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class EconomicsCalculationParameters:
    marketplace: str
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    estimated_monthly_sales: int
    competitor_count: int
    risk_level: str
    context_items: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.marketplace, "marketplace")
        _decimal(self.minimum_net_profit, "minimum_net_profit")
        _decimal(self.minimum_roi, "minimum_roi")
        for name in ("estimated_monthly_sales", "competitor_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        _required_text(self.risk_level, "risk_level")
        if not isinstance(self.context_items, tuple):
            raise TypeError("context_items must be a tuple")
        keys: list[str] = []
        for item in self.context_items:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError("context_items must contain key/value tuples")
            key, value = item
            _required_text(key, "context key")
            if not _immutable_context_value(value):
                raise TypeError("context values must be deeply immutable scalars or tuples")
            keys.append(key)
        if len(set(keys)) != len(keys):
            raise ValueError("context keys must be unique")


@dataclass(frozen=True, slots=True)
class ProfitabilityResultSnapshot:
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    passes_net_profit_filter: bool
    passes_roi_filter: bool
    passes_profitability_filter: bool

    def __post_init__(self) -> None:
        _decimal(self.minimum_net_profit, "minimum_net_profit")
        _decimal(self.minimum_roi, "minimum_roi")
        for name in (
            "passes_net_profit_filter",
            "passes_roi_filter",
            "passes_profitability_filter",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if self.passes_profitability_filter != (
            self.passes_net_profit_filter and self.passes_roi_filter
        ):
            raise ValueError("passes_profitability_filter must match component filters")


@dataclass(frozen=True, slots=True)
class EconomicsCalculationSnapshot:
    snapshot_id: str
    opportunity_identity: OpportunityIdentity
    market_observation_identity: MarketObservationIdentity
    candidate_opportunity_binding_id: str
    candidate_id: str
    price_intelligence_snapshot_id: str
    verified_economics_opportunity_id: str
    revenue: MoneyInput
    marketplace_fee: MoneyInput
    payment_fee: MoneyInput
    tax_cost: MoneyInput
    landed_cost: MoneyInput
    selling_cost: MoneyInput
    total_cost: MoneyInput
    net_profit: MoneyInput
    roi: Decimal
    landed_cost_roi: Decimal
    margin_rate: Decimal
    break_even: MoneyInput
    profitability_result: ProfitabilityResultSnapshot
    calculation_parameters: EconomicsCalculationParameters
    analysis: EconomicsAnalysisSnapshot
    calculation_version: str
    generated_at: datetime
    schema_version: str = ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "snapshot_id",
            "candidate_opportunity_binding_id",
            "candidate_id",
            "price_intelligence_snapshot_id",
            "verified_economics_opportunity_id",
            "calculation_version",
            "schema_version",
        ):
            _required_text(getattr(self, name), name)
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        money_names = (
            "revenue",
            "marketplace_fee",
            "payment_fee",
            "tax_cost",
            "landed_cost",
            "selling_cost",
            "total_cost",
            "net_profit",
            "break_even",
        )
        currencies: set[str] = set()
        for name in money_names:
            value = getattr(self, name)
            if not isinstance(value, MoneyInput):
                raise TypeError(f"{name} must be MoneyInput")
            currencies.add(value.currency)
        if len(currencies) != 1:
            raise ValueError("all snapshot MoneyInput values must use one currency")
        for name in ("roi", "landed_cost_roi", "margin_rate"):
            _decimal(getattr(self, name), name)
        if not isinstance(self.profitability_result, ProfitabilityResultSnapshot):
            raise TypeError("profitability_result must be ProfitabilityResultSnapshot")
        if not isinstance(self.calculation_parameters, EconomicsCalculationParameters):
            raise TypeError("calculation_parameters must be EconomicsCalculationParameters")
        if not isinstance(self.analysis, EconomicsAnalysisSnapshot):
            raise TypeError("analysis must be EconomicsAnalysisSnapshot")
        if (
            self.profitability_result.minimum_net_profit
            != self.calculation_parameters.minimum_net_profit
            or self.profitability_result.minimum_roi
            != self.calculation_parameters.minimum_roi
        ):
            raise ValueError("profitability thresholds must match calculation parameters")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
