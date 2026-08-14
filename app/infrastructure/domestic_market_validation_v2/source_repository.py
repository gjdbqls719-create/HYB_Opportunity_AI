"""Read-only production adapter for DMV v2 immutable source authorities."""

from __future__ import annotations


class DomesticMarketValidationV2SourceRepositoryAdapter:
    """Delegate DMV v2 source reads to their existing authority owners."""

    def __init__(self, target_bindings, competition, demand) -> None:
        self._target_bindings = target_bindings
        self._competition = competition
        self._demand = demand

    def get_target_binding(self, opportunity_id: str):
        return self._target_bindings.get_target_binding(opportunity_id)

    def get_competition_publication(self, observation_id: str):
        return self._competition.get_publication_by_observation_id(observation_id)

    def get_competition_authority_fingerprint(self, cohort_id: str):
        return self._competition.get_authority_fingerprint(cohort_id)

    def get_demand_publication(self, observation_id: str):
        return self._demand.get_publication(observation_id)

    def get_demand_authority_fingerprint(self, observation_id: str):
        return self._demand.get_authority_fingerprint(observation_id)
