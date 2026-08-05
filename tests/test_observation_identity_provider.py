from __future__ import annotations

from app.application.discovery import ObservationIdentityProvider


class StubObservationIdentityProvider:
    def __init__(self, observation_id: str) -> None:
        self.observation_id = observation_id
        self.calls = 0

    def provide_observation_id(self) -> str:
        self.calls += 1
        return self.observation_id


def test_observation_identity_provider_supplies_caller_owned_opaque_identity() -> None:
    provider = StubObservationIdentityProvider("observation-issued-1")

    assert isinstance(provider, ObservationIdentityProvider)
    assert provider.provide_observation_id() == "observation-issued-1"
    assert provider.calls == 1


def test_observation_identity_provider_rejects_objects_without_the_port() -> None:
    assert not isinstance(object(), ObservationIdentityProvider)
