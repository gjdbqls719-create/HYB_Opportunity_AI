from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def _normalize_text(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> str:
    """
    문자열 입력을 공백 제거 및 소문자 형태로 정규화한다.
    """
    if value is None:
        normalized = ""
    else:
        normalized = str(value).strip().lower()

    if not allow_empty and not normalized:
        raise ValueError(
            f"{field_name}은(는) 비어 있을 수 없습니다."
        )

    return normalized


def _normalize_optional_text(
    value: Any,
) -> str | None:
    """
    선택적 문자열을 정규화한다.

    None 또는 빈 문자열은 None으로 변환한다.
    """
    if value is None:
        return None

    normalized = str(value).strip().lower()

    if not normalized:
        return None

    return normalized


def _normalize_optional_rate(
    value: Any,
    field_name: str,
) -> Decimal | None:
    """
    선택적 수수료율을 Decimal로 변환하고
    0 이상 1 이하인지 검증한다.
    """
    if value is None:
        return None

    try:
        normalized = Decimal(str(value))
    except Exception as error:
        raise ValueError(
            f"{field_name}은(는) 숫자여야 합니다."
        ) from error

    if not Decimal("0") <= normalized <= Decimal("1"):
        raise ValueError(
            f"{field_name}은(는) 0 이상 1 이하여야 합니다."
        )

    return normalized


def _normalize_optional_money(
    value: Any,
    field_name: str,
) -> Decimal | None:
    """
    선택적 금액을 Decimal로 변환하고
    음수인지 검증한다.
    """
    if value is None:
        return None

    try:
        normalized = Decimal(str(value))
    except Exception as error:
        raise ValueError(
            f"{field_name}은(는) 숫자여야 합니다."
        ) from error

    if normalized < 0:
        raise ValueError(
            f"{field_name}은(는) 0 이상이어야 합니다."
        )

    return normalized


@dataclass(frozen=True, slots=True)
class MarketplaceRule:
    """
    마켓플레이스의 특정 조건에 적용되는 규칙.

    category와 country_code가 None이면
    해당 마켓플레이스의 기본 규칙으로 사용할 수 있다.

    수수료 값이 None이면 기존 FeeProfile 값을
    그대로 사용한다.
    """

    marketplace: str

    category: str | None = None
    country_code: str | None = None

    marketplace_fee_rate: Decimal | None = None
    payment_fee_rate: Decimal | None = None
    fixed_fee: Decimal | None = None

    priority: int = 0
    enabled: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        marketplace = _normalize_text(
            self.marketplace,
            "마켓플레이스",
        )

        category = _normalize_optional_text(
            self.category
        )

        country_code = _normalize_optional_text(
            self.country_code
        )

        if country_code is not None:
            country_code = country_code.upper()

            if len(country_code) != 2:
                raise ValueError(
                    "국가 코드는 2자리여야 합니다."
                )

        marketplace_fee_rate = (
            _normalize_optional_rate(
                self.marketplace_fee_rate,
                "마켓플레이스 수수료율",
            )
        )

        payment_fee_rate = (
            _normalize_optional_rate(
                self.payment_fee_rate,
                "결제 수수료율",
            )
        )

        fixed_fee = _normalize_optional_money(
            self.fixed_fee,
            "고정 수수료",
        )

        try:
            priority = int(self.priority)
        except Exception as error:
            raise ValueError(
                "우선순위는 정수여야 합니다."
            ) from error

        description = str(
            self.description or ""
        ).strip()

        object.__setattr__(
            self,
            "marketplace",
            marketplace,
        )
        object.__setattr__(
            self,
            "category",
            category,
        )
        object.__setattr__(
            self,
            "country_code",
            country_code,
        )
        object.__setattr__(
            self,
            "marketplace_fee_rate",
            marketplace_fee_rate,
        )
        object.__setattr__(
            self,
            "payment_fee_rate",
            payment_fee_rate,
        )
        object.__setattr__(
            self,
            "fixed_fee",
            fixed_fee,
        )
        object.__setattr__(
            self,
            "priority",
            priority,
        )
        object.__setattr__(
            self,
            "enabled",
            bool(self.enabled),
        )
        object.__setattr__(
            self,
            "description",
            description,
        )

    @property
    def specificity(self) -> int:
        """
        규칙이 얼마나 구체적인지 나타낸다.

        카테고리와 국가 조건이 많을수록
        더 구체적인 규칙이다.
        """
        score = 0

        if self.category is not None:
            score += 1

        if self.country_code is not None:
            score += 1

        return score

    def matches(
        self,
        *,
        marketplace: str,
        category: str | None = None,
        country_code: str | None = None,
    ) -> bool:
        """
        주어진 상품 조건에 이 규칙이 일치하는지 확인한다.
        """
        if not self.enabled:
            return False

        normalized_marketplace = _normalize_text(
            marketplace,
            "마켓플레이스",
        )

        normalized_category = _normalize_optional_text(
            category
        )

        normalized_country_code = (
            _normalize_optional_text(
                country_code
            )
        )

        if normalized_country_code is not None:
            normalized_country_code = (
                normalized_country_code.upper()
            )

        if self.marketplace != normalized_marketplace:
            return False

        if (
            self.category is not None
            and self.category != normalized_category
        ):
            return False

        if (
            self.country_code is not None
            and self.country_code
            != normalized_country_code
        ):
            return False

        return True

    def to_fee_overrides(
        self,
    ) -> dict[str, Decimal]:
        """
        Fee Engine에 전달할 수수료 재정의 값만 반환한다.
        """
        overrides: dict[str, Decimal] = {}

        if self.marketplace_fee_rate is not None:
            overrides[
                "marketplace_fee_rate"
            ] = self.marketplace_fee_rate

        if self.payment_fee_rate is not None:
            overrides[
                "payment_fee_rate"
            ] = self.payment_fee_rate

        if self.fixed_fee is not None:
            overrides[
                "fixed_fee"
            ] = self.fixed_fee

        return overrides


@dataclass(frozen=True, slots=True)
class ResolvedMarketplaceRule:
    """
    Rules Engine이 최종 선택한 규칙 결과.
    """

    marketplace: str
    category: str | None
    country_code: str | None
    rule: MarketplaceRule | None
    source: str

    def __post_init__(self) -> None:
        marketplace = _normalize_text(
            self.marketplace,
            "마켓플레이스",
        )

        category = _normalize_optional_text(
            self.category
        )

        country_code = _normalize_optional_text(
            self.country_code
        )

        if country_code is not None:
            country_code = country_code.upper()

        source = _normalize_text(
            self.source,
            "규칙 출처",
        )

        if source not in {
            "matched",
            "default",
            "none",
        }:
            raise ValueError(
                "규칙 출처는 matched, default, "
                "none 중 하나여야 합니다."
            )

        object.__setattr__(
            self,
            "marketplace",
            marketplace,
        )
        object.__setattr__(
            self,
            "category",
            category,
        )
        object.__setattr__(
            self,
            "country_code",
            country_code,
        )
        object.__setattr__(
            self,
            "source",
            source,
        )

    @property
    def has_rule(self) -> bool:
        """
        적용할 규칙이 존재하는지 반환한다.
        """
        return self.rule is not None

    def to_fee_overrides(
        self,
    ) -> dict[str, Decimal]:
        """
        선택된 규칙을 Fee Engine 재정의 값으로 변환한다.
        """
        if self.rule is None:
            return {}

        return self.rule.to_fee_overrides()