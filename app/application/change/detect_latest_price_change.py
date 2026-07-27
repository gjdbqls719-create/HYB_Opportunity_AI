from __future__ import annotations

from app.application.change.detect_changes import (
    DetectChangesUseCase,
)
from app.application.change.models import (
    ChangeDetectionResponse,
    SnapshotPair,
)
from app.application.change.ports import (
    PriceSnapshotProvider,
)
from market_data.price_snapshot import PriceSnapshot


class DetectLatestPriceChangeUseCase:
    """
    현재 PriceSnapshot에 대응하는 이전 가격 Snapshot을 조회하고
    기존 DetectChangesUseCase를 통해 가격 변화를 탐지한다.

    책임:
    - 동일 Marketplace Listing의 이전 Snapshot 조회
    - 이전·현재 SnapshotPair 구성
    - 기존 Change Detection Use Case 실행

    책임이 아닌 것:
    - Snapshot 저장
    - Discovery 실행
    - 가격 변화 계산 로직
    - Domain Event 직접 생성
    """

    def __init__(
        self,
        *,
        snapshot_provider: PriceSnapshotProvider,
        change_detector: DetectChangesUseCase | None = None,
    ) -> None:
        self._validate_provider(snapshot_provider)

        if (
            change_detector is not None
            and not isinstance(
                change_detector,
                DetectChangesUseCase,
            )
        ):
            raise TypeError(
                "change_detector는 "
                "DetectChangesUseCase 또는 None이어야 합니다."
            )

        self._snapshot_provider = snapshot_provider
        self._change_detector = (
            change_detector
            if change_detector is not None
            else DetectChangesUseCase()
        )

    def execute(
        self,
        *,
        current_snapshot: PriceSnapshot,
    ) -> ChangeDetectionResponse:
        """
        현재 가격 Snapshot과 동일한 Listing의
        가장 최근 과거 Snapshot을 비교한다.

        과거 Snapshot이 없으면 최초 관찰로 간주하며,
        비교되지 않은 빈 ChangeDetectionResponse를 반환한다.
        """
        if not isinstance(
            current_snapshot,
            PriceSnapshot,
        ):
            raise TypeError(
                "current_snapshot은 "
                "PriceSnapshot이어야 합니다."
            )

        previous_snapshot = (
            self._snapshot_provider
            .get_latest_for_listing(
                marketplace=(
                    current_snapshot.marketplace
                ),
                item_id=current_snapshot.item_id,
            )
        )

        if previous_snapshot is None:
            return ChangeDetectionResponse(
                change_sets=(),
                events=(),
            )

        if not isinstance(
            previous_snapshot,
            PriceSnapshot,
        ):
            raise TypeError(
                "PriceSnapshotProvider는 "
                "PriceSnapshot 또는 None을 반환해야 합니다."
            )

        snapshot_pair = SnapshotPair(
            previous=previous_snapshot,
            current=current_snapshot,
        )

        return self._change_detector.execute(
            snapshot_pairs=(snapshot_pair,),
        )

    @staticmethod
    def _validate_provider(
        snapshot_provider: PriceSnapshotProvider,
    ) -> None:
        if snapshot_provider is None:
            raise TypeError(
                "snapshot_provider가 필요합니다."
            )

        get_latest_for_listing = getattr(
            snapshot_provider,
            "get_latest_for_listing",
            None,
        )
        get_latest_for_canonical_product = getattr(
            snapshot_provider,
            "get_latest_for_canonical_product",
            None,
        )

        if not callable(get_latest_for_listing):
            raise TypeError(
                "snapshot_provider는 "
                "get_latest_for_listing()을 제공해야 합니다."
            )

        if not callable(
            get_latest_for_canonical_product
        ):
            raise TypeError(
                "snapshot_provider는 "
                "get_latest_for_canonical_product()를 "
                "제공해야 합니다."
            )