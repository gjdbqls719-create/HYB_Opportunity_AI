from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from uuid import uuid4

from app.models import Product


def utc_now() -> datetime:
    """현재 UTC 시각을 timezone-aware datetime으로 반환한다."""
    return datetime.now(timezone.utc)


class WatchIdentityStrength(StrEnum):
    """
    Watch Item이 사용하는 상품 식별자의 신뢰 수준.

    STRONG:
        Canonical Product Domain에서 확정한 상품 식별자.

    LISTING:
        특정 Marketplace의 개별 Listing 식별자.

    WEAK:
        제목과 같은 약한 정보만으로 만든 임시 식별자.
    """

    STRONG = "strong"
    LISTING = "listing"
    WEAK = "weak"


class WatchItemStatus(StrEnum):
    """Watch Item의 수명주기 상태."""

    WATCHING = "watching"
    ARCHIVED = "archived"


@dataclass(slots=True)
class WatchItem:
    """
    지속적으로 관찰할 하나의 Marketplace 상품.

    Watch List는 상품 분석 결과 전체를 저장하지 않는다.
    상품을 다시 조회하고 재평가하는 데 필요한 최소 정보와
    사용자의 감시 조건만 보관한다.

    canonical_product_id가 제공되면 Strong Identity로 취급한다.
    그렇지 않으면 Marketplace Listing Identity를 사용한다.
    """

    marketplace: str
    item_id: str
    title: str
    current_price: float
    currency: str

    url: str = ""
    canonical_product_id: str | None = None
    brand: str | None = None
    model_number: str | None = None

    target_roi: float | None = None
    target_net_profit: float | None = None
    note: str = ""

    watch_id: str = field(
        default_factory=lambda: uuid4().hex
    )
    status: WatchItemStatus = WatchItemStatus.WATCHING
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    last_analyzed_at: datetime | None = None

    def __post_init__(self) -> None:
        self.marketplace = self.marketplace.strip().lower()
        self.item_id = self.item_id.strip()
        self.title = self.title.strip()
        self.currency = self.currency.strip().upper()
        self.url = self.url.strip()
        self.note = self.note.strip()
        self.watch_id = self.watch_id.strip()

        if self.canonical_product_id is not None:
            cleaned_canonical_id = self.canonical_product_id.strip()
            self.canonical_product_id = cleaned_canonical_id or None

        if self.brand is not None:
            cleaned_brand = self.brand.strip()
            self.brand = cleaned_brand or None

        if self.model_number is not None:
            cleaned_model_number = self.model_number.strip()
            self.model_number = cleaned_model_number or None

        if not self.marketplace:
            raise ValueError("marketplace는 비어 있을 수 없습니다.")

        if not self.title:
            raise ValueError("title은 비어 있을 수 없습니다.")

        if not self.currency:
            raise ValueError("currency는 비어 있을 수 없습니다.")

        if not self.watch_id:
            raise ValueError("watch_id는 비어 있을 수 없습니다.")

        self.current_price = self._validate_non_negative_number(
            self.current_price,
            field_name="current_price",
        )

        if self.target_roi is not None:
            self.target_roi = self._validate_non_negative_number(
                self.target_roi,
                field_name="target_roi",
            )

        if self.target_net_profit is not None:
            self.target_net_profit = self._validate_non_negative_number(
                self.target_net_profit,
                field_name="target_net_profit",
            )

        self._validate_datetime(
            self.created_at,
            field_name="created_at",
        )
        self._validate_datetime(
            self.updated_at,
            field_name="updated_at",
        )

        if self.last_analyzed_at is not None:
            self._validate_datetime(
                self.last_analyzed_at,
                field_name="last_analyzed_at",
            )

        if self.updated_at < self.created_at:
            raise ValueError(
                "updated_at은 created_at보다 빠를 수 없습니다."
            )

        if (
            self.last_analyzed_at is not None
            and self.last_analyzed_at < self.created_at
        ):
            raise ValueError(
                "last_analyzed_at은 created_at보다 빠를 수 없습니다."
            )

        if not isinstance(self.status, WatchItemStatus):
            raise TypeError(
                "status는 WatchItemStatus여야 합니다."
            )

    @classmethod
    def from_product(
        cls,
        product: Product,
        *,
        canonical_product_id: str | None = None,
        target_roi: float | None = None,
        target_net_profit: float | None = None,
        note: str = "",
        created_at: datetime | None = None,
    ) -> WatchItem:
        """Marketplace Product로부터 Watch Item을 생성한다."""
        if not isinstance(product, Product):
            raise TypeError("product는 Product여야 합니다.")

        resolved_created_at = created_at or utc_now()

        return cls(
            marketplace=product.marketplace,
            item_id=product.item_id,
            title=product.title,
            current_price=product.price,
            currency=product.currency,
            url=product.url,
            canonical_product_id=canonical_product_id,
            brand=product.brand,
            model_number=product.model_number,
            target_roi=target_roi,
            target_net_profit=target_net_profit,
            note=note,
            created_at=resolved_created_at,
            updated_at=resolved_created_at,
        )

    @property
    def identity_strength(self) -> WatchIdentityStrength:
        """
        현재 Watch Item이 사용하는 식별자의 신뢰 수준을 반환한다.

        brand와 model_number가 있더라도 capacity, edition 등
        필요한 Strong Identity 정보가 모두 검증되었다고 볼 수 없으므로
        자동으로 Strong Identity를 만들지 않는다.
        """
        if self.canonical_product_id is not None:
            return WatchIdentityStrength.STRONG

        if self.item_id or self.url:
            return WatchIdentityStrength.LISTING

        return WatchIdentityStrength.WEAK

    @property
    def identity_key(self) -> str:
        """
        중복 판정과 저장소 조회에 사용할 안정적인 식별자를 반환한다.

        우선순위:
        1. Canonical Product ID
        2. Marketplace + Item ID
        3. Marketplace + URL
        4. Marketplace + 정규화된 제목
        """
        if self.canonical_product_id is not None:
            return f"canonical:{self.canonical_product_id.casefold()}"

        if self.item_id:
            return (
                f"listing:{self.marketplace}:"
                f"{self.item_id.casefold()}"
            )

        if self.url:
            return (
                f"listing-url:{self.marketplace}:"
                f"{self.url.casefold()}"
            )

        normalized_title = " ".join(
            self.title.casefold().split()
        )

        return (
            f"weak-title:{self.marketplace}:"
            f"{normalized_title}"
        )

    @property
    def is_active(self) -> bool:
        return self.status is WatchItemStatus.WATCHING

    def archive(
        self,
        *,
        changed_at: datetime | None = None,
    ) -> None:
        """Watch Item을 보관 상태로 변경한다."""
        if self.status is WatchItemStatus.ARCHIVED:
            return

        self.status = WatchItemStatus.ARCHIVED
        self._touch(changed_at)

    def restore(
        self,
        *,
        changed_at: datetime | None = None,
    ) -> None:
        """보관된 Watch Item을 다시 감시 상태로 변경한다."""
        if self.status is WatchItemStatus.WATCHING:
            return

        self.status = WatchItemStatus.WATCHING
        self._touch(changed_at)

    def update_targets(
        self,
        *,
        target_roi: float | None,
        target_net_profit: float | None,
        changed_at: datetime | None = None,
    ) -> None:
        """사용자가 설정한 목표 수익 조건을 변경한다."""
        if target_roi is not None:
            target_roi = self._validate_non_negative_number(
                target_roi,
                field_name="target_roi",
            )

        if target_net_profit is not None:
            target_net_profit = self._validate_non_negative_number(
                target_net_profit,
                field_name="target_net_profit",
            )

        self.target_roi = target_roi
        self.target_net_profit = target_net_profit
        self._touch(changed_at)

    def update_note(
        self,
        note: str,
        *,
        changed_at: datetime | None = None,
    ) -> None:
        """사용자 메모를 변경한다."""
        if not isinstance(note, str):
            raise TypeError("note는 문자열이어야 합니다.")

        self.note = note.strip()
        self._touch(changed_at)

    def record_analysis(
        self,
        *,
        observed_price: float,
        analyzed_at: datetime | None = None,
    ) -> None:
        """재분석 결과에서 최신 관측 가격과 분석 시각을 기록한다."""
        resolved_analyzed_at = analyzed_at or utc_now()

        self._validate_datetime(
            resolved_analyzed_at,
            field_name="analyzed_at",
        )

        if resolved_analyzed_at < self.created_at:
            raise ValueError(
                "analyzed_at은 created_at보다 빠를 수 없습니다."
            )

        self.current_price = self._validate_non_negative_number(
            observed_price,
            field_name="observed_price",
        )
        self.last_analyzed_at = resolved_analyzed_at
        self.updated_at = resolved_analyzed_at

    def _touch(
        self,
        changed_at: datetime | None,
    ) -> None:
        resolved_changed_at = changed_at or utc_now()

        self._validate_datetime(
            resolved_changed_at,
            field_name="changed_at",
        )

        if resolved_changed_at < self.updated_at:
            raise ValueError(
                "changed_at은 현재 updated_at보다 빠를 수 없습니다."
            )

        self.updated_at = resolved_changed_at

    @staticmethod
    def _validate_non_negative_number(
        value: float,
        *,
        field_name: str,
    ) -> float:
        try:
            resolved_value = float(value)
        except (TypeError, ValueError) as error:
            raise TypeError(
                f"{field_name}는 숫자여야 합니다."
            ) from error

        if not isfinite(resolved_value):
            raise ValueError(
                f"{field_name}는 유한한 숫자여야 합니다."
            )

        if resolved_value < 0:
            raise ValueError(
                f"{field_name}는 0 이상이어야 합니다."
            )

        return resolved_value

    @staticmethod
    def _validate_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        if not isinstance(value, datetime):
            raise TypeError(
                f"{field_name}은 datetime이어야 합니다."
            )

        if value.tzinfo is None:
            raise ValueError(
                f"{field_name}은 timezone-aware datetime이어야 합니다."
            )