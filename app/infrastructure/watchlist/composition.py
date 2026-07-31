from __future__ import annotations

from pathlib import Path

from app.application.change import (
    DetectLatestPriceChangeUseCase,
)
from app.application.watchlist import (
    LatestPriceChangeDetector,
    ListingLookupPort,
    PriceObservationRecorder,
    WatchListMonitorUseCase,
    WatchListRepository,
)
from app.infrastructure.change import (
    PriceHistorySnapshotProvider,
)
from app.infrastructure.watchlist.marketplace_readers import (
    create_marketplace_listing_lookup_adapter,
)
from app.infrastructure.watchlist.price_observation_recorder import (
    PriceHistoryObservationRecorder,
)
from app.infrastructure.watchlist.sqlite_repository import (
    SQLiteWatchListRepository,
)
from storage.price_history import (
    DEFAULT_DATABASE_PATH,
    PriceHistoryRepository,
)


def create_watchlist_monitor(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    *,
    repository: WatchListRepository | None = None,
    listing_lookup: ListingLookupPort | None = None,
    change_detector: LatestPriceChangeDetector | None = None,
    price_observation_recorder: PriceObservationRecorder | None = None,
) -> WatchListMonitorUseCase:
    """실제 Infrastructure 구현체로 WatchList Monitor를 조립한다."""

    resolved_repository = (
        repository
        if repository is not None
        else SQLiteWatchListRepository(database_path)
    )
    resolved_listing_lookup = (
        listing_lookup
        if listing_lookup is not None
        else create_marketplace_listing_lookup_adapter()
    )

    price_history_repository = PriceHistoryRepository(database_path)

    if change_detector is None:
        snapshot_provider = PriceHistorySnapshotProvider(
            repository=price_history_repository,
        )
        resolved_change_detector = (
            DetectLatestPriceChangeUseCase(
                snapshot_provider=snapshot_provider,
            )
        )
    else:
        resolved_change_detector = change_detector

    resolved_price_observation_recorder = (
        price_observation_recorder
        if price_observation_recorder is not None
        else PriceHistoryObservationRecorder(
            repository=price_history_repository,
        )
    )

    return WatchListMonitorUseCase(
        repository=resolved_repository,
        listing_lookup=resolved_listing_lookup,
        change_detector=resolved_change_detector,
        price_observation_recorder=(
            resolved_price_observation_recorder
        ),
    )
