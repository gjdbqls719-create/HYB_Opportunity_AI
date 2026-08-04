"""Production discovery runtime backed by the existing engine orchestrator."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.domain.discovery import DiscoveryResult
from app.domain.discovery_identity import DiscoveryCommand
from app.infrastructure.discovery.orchestrator_gateway import (
    opportunity_result_to_discovery_result,
)
from engine.orchestrator import OpportunityResult, find_best_opportunities


OpportunityFinder = Callable[..., list[OpportunityResult]]


class OrchestratorProductionDiscoveryRuntime:
    """Executes one persisted DiscoveryCommand through the existing engine."""

    def __init__(
        self,
        *,
        finder: OpportunityFinder = find_best_opportunities,
        price_history_repository: Any | None = None,
        search_error_handler: Any | None = None,
        opportunity_history_repository: Any | None = None,
        ai_memory_history: Sequence[Any] | None = None,
        currency_converter: Any | None = None,
    ) -> None:
        self._finder = finder
        self._price_history_repository = price_history_repository
        self._search_error_handler = search_error_handler
        self._opportunity_history_repository = opportunity_history_repository
        self._ai_memory_history = ai_memory_history
        self._currency_converter = currency_converter

    def execute(
        self,
        command: DiscoveryCommand,
    ) -> tuple[DiscoveryResult, ...]:
        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")

        parameters = command.parameters
        opportunities = self._finder(
            query=parameters.query,
            selling_price_multiplier=float(
                parameters.selling_price_multiplier
            ),
            shipping_cost=(
                None
                if parameters.shipping_cost is None
                else float(parameters.shipping_cost)
            ),
            marketplace_fee_rate=float(parameters.marketplace_fee_rate),
            payment_fee_rate=float(parameters.payment_fee_rate),
            fixed_fee=(
                None
                if parameters.fixed_fee is None
                else float(parameters.fixed_fee)
            ),
            marketplace_fee_known=parameters.marketplace_fee_known,
            payment_fee_known=parameters.payment_fee_known,
            fixed_fee_known=parameters.fixed_fee_known,
            tax_rate=float(parameters.tax_rate),
            other_cost=float(parameters.other_cost),
            minimum_net_profit=float(parameters.minimum_net_profit),
            minimum_roi=float(parameters.minimum_roi),
            estimated_monthly_sales=parameters.estimated_monthly_sales,
            competitor_count=parameters.competitor_count,
            risk_level=parameters.risk_level,
            limit=parameters.limit,
            match_threshold=float(parameters.match_threshold),
            price_history_repository=self._price_history_repository,
            search_error_handler=self._search_error_handler,
            opportunity_history_repository=self._opportunity_history_repository,
            ai_memory_history=self._ai_memory_history,
            currency_converter=self._currency_converter,
            target_currency=parameters.target_currency,
        )

        return tuple(
            opportunity_result_to_discovery_result(opportunity)
            for opportunity in opportunities
        )


__all__ = ["OrchestratorProductionDiscoveryRuntime"]
