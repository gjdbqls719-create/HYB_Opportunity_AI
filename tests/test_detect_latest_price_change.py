from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.change import (
    DetectChangesUseCase,
    DetectLatestPriceChangeUseCase,
)
from market_data.price_snapshot import PriceSnapshot


PREVIOUS_TIME = datetime(
    2026,
    7,
    27,
    10,
    0,
    tzinfo=timezone.utc,
)

CURRENT_TIME = datetime(
    2026,
    7,
    27,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_price_snapshot(
    *,
    snapshot_id: str,
    price: Decimal,
    observed_at: datetime,
    canonical_product_id: str = "canonical_001",
    marketplace: str = "ebay",
    item_id: str = "item_001",
) -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id=snapshot_id,
        canonical_product_id=canonical_product_id,
        marketplace=marketplace,
        observed_at=observed_at,
        source_url=(
            f"https://example.com/{item_id}"
        ),
        item_id=item_id,
        price=price,
        currency="USD",
        condition="new",
        seller_id="seller_001",
    )


class FakePriceSnapshotProvider:
    def __init__(
        self,
        snapshot: PriceSnapshot | None,
    ) -> None:
        self.snapshot = snapshot
        self.listing_calls: list[
            tuple[str, str]
        ] = []

    def get_latest_for_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
    ) -> PriceSnapshot | None:
        self.listing_calls.append(
            (marketplace, item_id)
        )
        return self.snapshot

    def get_latest_for_canonical_product(
        self,
        *,
        canonical_product_id: str,
    ) -> PriceSnapshot | None:
        return self.snapshot


class InvalidProvider:
    pass


class InvalidReturnProvider:
    def get_latest_for_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
    ) -> object:
        return object()

    def get_latest_for_canonical_product(
        self,
        *,
        canonical_product_id: str,
    ) -> None:
        return None


def test_returns_empty_response_when_previous_snapshot_missing(
) -> None:
    provider = FakePriceSnapshotProvider(
        snapshot=None
    )
    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=provider
    )

    current = make_price_snapshot(
        snapshot_id="current",
        price=Decimal("90.00"),
        observed_at=CURRENT_TIME,
    )

    response = use_case.execute(
        current_snapshot=current
    )

    assert response.change_sets == ()
    assert response.events == ()
    assert response.compared_pair_count == 0
    assert response.changed_pair_count == 0
    assert response.change_count == 0
    assert response.event_count == 0
    assert response.has_changes is False


def test_queries_previous_snapshot_by_listing_identity(
) -> None:
    provider = FakePriceSnapshotProvider(
        snapshot=None
    )
    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=provider
    )

    current = make_price_snapshot(
        snapshot_id="current",
        marketplace="ebay",
        item_id="item_001",
        price=Decimal("90.00"),
        observed_at=CURRENT_TIME,
    )

    use_case.execute(
        current_snapshot=current
    )

    assert provider.listing_calls == [
        ("ebay", "item_001")
    ]


def test_detects_price_change_against_previous_snapshot(
) -> None:
    previous = make_price_snapshot(
        snapshot_id="previous",
        price=Decimal("100.00"),
        observed_at=PREVIOUS_TIME,
    )
    current = make_price_snapshot(
        snapshot_id="current",
        price=Decimal("90.00"),
        observed_at=CURRENT_TIME,
    )

    provider = FakePriceSnapshotProvider(
        snapshot=previous
    )
    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=provider
    )

    response = use_case.execute(
        current_snapshot=current
    )

    assert response.compared_pair_count == 1
    assert response.changed_pair_count == 1
    assert response.unchanged_pair_count == 0
    assert response.has_changes is True
    assert response.change_count >= 1
    assert response.event_count >= 1


def test_returns_unchanged_result_when_price_is_same(
) -> None:
    previous = make_price_snapshot(
        snapshot_id="previous",
        price=Decimal("100.00"),
        observed_at=PREVIOUS_TIME,
    )
    current = make_price_snapshot(
        snapshot_id="current",
        price=Decimal("100.00"),
        observed_at=CURRENT_TIME,
    )

    provider = FakePriceSnapshotProvider(
        snapshot=previous
    )
    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=provider
    )

    response = use_case.execute(
        current_snapshot=current
    )

    assert response.compared_pair_count == 1
    assert response.changed_pair_count == 0
    assert response.unchanged_pair_count == 1
    assert response.change_count == 0
    assert response.event_count == 0
    assert response.has_changes is False


def test_uses_injected_change_detector() -> None:
    previous = make_price_snapshot(
        snapshot_id="previous",
        price=Decimal("100.00"),
        observed_at=PREVIOUS_TIME,
    )
    provider = FakePriceSnapshotProvider(
        snapshot=previous
    )
    detector = DetectChangesUseCase()

    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=provider,
        change_detector=detector,
    )

    current = make_price_snapshot(
        snapshot_id="current",
        price=Decimal("80.00"),
        observed_at=CURRENT_TIME,
    )

    response = use_case.execute(
        current_snapshot=current
    )

    assert response.compared_pair_count == 1
    assert response.has_changes is True


def test_rejects_non_price_current_snapshot() -> None:
    provider = FakePriceSnapshotProvider(
        snapshot=None
    )
    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=provider
    )

    with pytest.raises(
        TypeError,
        match="PriceSnapshot",
    ):
        use_case.execute(
            current_snapshot=object(),  # type: ignore[arg-type]
        )


def test_rejects_provider_with_invalid_return_type(
) -> None:
    use_case = DetectLatestPriceChangeUseCase(
        snapshot_provider=(
            InvalidReturnProvider()
        )
    )

    current = make_price_snapshot(
        snapshot_id="current",
        price=Decimal("100.00"),
        observed_at=CURRENT_TIME,
    )

    with pytest.raises(
        TypeError,
        match="PriceSnapshotProvider",
    ):
        use_case.execute(
            current_snapshot=current
        )


def test_rejects_missing_provider() -> None:
    with pytest.raises(
        TypeError,
        match="snapshot_provider",
    ):
        DetectLatestPriceChangeUseCase(
            snapshot_provider=None,  # type: ignore[arg-type]
        )


def test_rejects_provider_without_required_methods(
) -> None:
    with pytest.raises(
        TypeError,
        match="get_latest_for_listing",
    ):
        DetectLatestPriceChangeUseCase(
            snapshot_provider=(
                InvalidProvider()
            )  # type: ignore[arg-type]
        )


def test_rejects_invalid_change_detector() -> None:
    provider = FakePriceSnapshotProvider(
        snapshot=None
    )

    with pytest.raises(
        TypeError,
        match="DetectChangesUseCase",
    ):
        DetectLatestPriceChangeUseCase(
            snapshot_provider=provider,
            change_detector=object(),  # type: ignore[arg-type]
        )