from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from types import MappingProxyType
from typing import Mapping

from app.models.canonical_product import CanonicalProduct
from engine.canonical_id_generator import CanonicalIdGenerator
from engine.catalog_repository import CatalogRepository
from engine.product_normalizer import normalize_title


def _normalize_optional_text(
    value: str | None,
    *,
    field_name: str,
) -> str | None:
    """
    선택 문자열을 검증하고 앞뒤 공백을 제거한다.

    공백만 존재하는 문자열은 None으로 변환한다.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name}은 문자열 또는 None이어야 합니다."
        )

    normalized = value.strip()

    if not normalized:
        return None

    return normalized


def _normalize_attributes(
    attributes: Mapping[str, str] | None,
) -> Mapping[str, str]:
    """
    CanonicalProductDraft의 확장 속성을 읽기 전용 Mapping으로 변환한다.
    """
    if attributes is None:
        return MappingProxyType({})

    if not isinstance(attributes, Mapping):
        raise TypeError(
            "attributes는 Mapping 객체여야 합니다."
        )

    normalized: dict[str, str] = {}

    for key, value in attributes.items():
        if not isinstance(key, str):
            raise TypeError(
                "attributes의 키는 문자열이어야 합니다."
            )

        if not isinstance(value, str):
            raise TypeError(
                "attributes의 값은 문자열이어야 합니다."
            )

        normalized_key = key.strip()
        normalized_value = value.strip()

        if not normalized_key:
            raise ValueError(
                "attributes의 키는 비어 있을 수 없습니다."
            )

        if not normalized_value:
            raise ValueError(
                "attributes의 값은 비어 있을 수 없습니다."
            )

        normalized[normalized_key] = normalized_value

    return MappingProxyType(normalized)


def _normalize_identity_value(
    value: str | None,
) -> str:
    """
    상품 식별 비교에 사용할 문자열을 정규화한다.
    """
    if value is None:
        return ""

    return normalize_title(value)


@dataclass(frozen=True, slots=True)
class CanonicalProductDraft:
    """
    CanonicalProduct 생성 전 단계의 상품 정보.

    display_id, 내부 UUID, 생성 시각은 포함하지 않는다.
    해당 정보는 CatalogManager가 생성 과정에서 부여한다.
    """

    brand: str | None = None
    model: str | None = None
    category: str | None = None

    capacity: str | None = None
    color: str | None = None
    size: str | None = None
    edition: str | None = None
    condition: str | None = None

    attributes: Mapping[str, str] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        text_fields = (
            "brand",
            "model",
            "category",
            "capacity",
            "color",
            "size",
            "edition",
            "condition",
        )

        for field_name in text_fields:
            normalized_value = _normalize_optional_text(
                getattr(self, field_name),
                field_name=field_name,
            )

            object.__setattr__(
                self,
                field_name,
                normalized_value,
            )

        object.__setattr__(
            self,
            "attributes",
            _normalize_attributes(
                self.attributes
            ),
        )

        if not self.has_identity_information:
            raise ValueError(
                "CanonicalProductDraft에는 최소 하나 이상의 "
                "상품 식별 정보가 필요합니다."
            )

    @property
    def has_identity_information(self) -> bool:
        """
        상품을 식별할 수 있는 정보가 하나 이상 존재하는지 반환한다.
        """
        return any(
            (
                self.brand,
                self.model,
                self.category,
                self.capacity,
                self.color,
                self.size,
                self.edition,
                self.condition,
                bool(self.attributes),
            )
        )


@dataclass(frozen=True, slots=True)
class CatalogResult:
    """
    CatalogManager의 find_or_create 결과.

    product:
        조회되거나 새로 생성된 CanonicalProduct.

    created:
        새로운 상품이 생성되었으면 True,
        기존 상품이 반환되었으면 False.
    """

    product: CanonicalProduct
    created: bool


class CatalogManager:
    """
    Canonical Product Catalog의 비즈니스 로직을 담당한다.

    주요 책임:

    - 기존 CanonicalProduct 검색
    - 신규 display_id 발급
    - CanonicalProduct 생성
    - Repository 저장
    - 중복 생성 방지

    Repository는 저장만 담당하고,
    동일 상품 판단과 생성 흐름은 CatalogManager가 담당한다.
    """

    def __init__(
        self,
        *,
        repository: CatalogRepository,
        id_generator: CanonicalIdGenerator,
    ) -> None:
        if not isinstance(
            repository,
            CatalogRepository,
        ):
            raise TypeError(
                "repository는 CatalogRepository 구현체여야 합니다."
            )

        if not isinstance(
            id_generator,
            CanonicalIdGenerator,
        ):
            raise TypeError(
                "id_generator는 CanonicalIdGenerator 구현체여야 합니다."
            )

        self._repository = repository
        self._id_generator = id_generator
        self._lock = RLock()

        self._synchronize_id_generator()

    @property
    def repository(self) -> CatalogRepository:
        """
        CatalogManager가 사용하는 Repository를 반환한다.
        """
        return self._repository

    @property
    def id_generator(self) -> CanonicalIdGenerator:
        """
        CatalogManager가 사용하는 ID Generator를 반환한다.
        """
        return self._id_generator

    def _synchronize_id_generator(self) -> None:
        """
        Repository에 저장된 기존 display_id와 ID 생성기를 동기화한다.

        현재 InMemoryCanonicalIdGenerator가 synchronize를 지원하지만,
        향후 다른 Generator 구현체도 사용할 수 있도록 기능 존재 여부를
        확인한 뒤 호출한다.
        """
        synchronize = getattr(
            self._id_generator,
            "synchronize",
            None,
        )

        if not callable(synchronize):
            return

        existing_display_ids = (
            product.display_id
            for product in self._repository.list_all()
        )

        synchronize(existing_display_ids)

    @staticmethod
    def _build_identity_key_from_draft(
        draft: CanonicalProductDraft,
    ) -> tuple[object, ...]:
        """
        Draft의 상품 동일성 비교 키를 생성한다.

        상품의 잘못된 병합을 피하기 위해 모든 식별 필드와
        확장 속성이 동일할 때만 같은 CanonicalProduct로 판단한다.
        """
        normalized_attributes = tuple(
            sorted(
                (
                    _normalize_identity_value(key),
                    _normalize_identity_value(value),
                )
                for key, value in draft.attributes.items()
            )
        )

        return (
            _normalize_identity_value(draft.brand),
            _normalize_identity_value(draft.model),
            _normalize_identity_value(draft.category),
            _normalize_identity_value(draft.capacity),
            _normalize_identity_value(draft.color),
            _normalize_identity_value(draft.size),
            _normalize_identity_value(draft.edition),
            _normalize_identity_value(draft.condition),
            normalized_attributes,
        )

    @staticmethod
    def _build_identity_key_from_product(
        product: CanonicalProduct,
    ) -> tuple[object, ...]:
        """
        저장된 CanonicalProduct의 상품 동일성 비교 키를 생성한다.
        """
        normalized_attributes = tuple(
            sorted(
                (
                    _normalize_identity_value(key),
                    _normalize_identity_value(value),
                )
                for key, value in product.attributes.items()
            )
        )

        return (
            _normalize_identity_value(product.brand),
            _normalize_identity_value(product.model),
            _normalize_identity_value(product.category),
            _normalize_identity_value(product.capacity),
            _normalize_identity_value(product.color),
            _normalize_identity_value(product.size),
            _normalize_identity_value(product.edition),
            _normalize_identity_value(product.condition),
            normalized_attributes,
        )

    def find(
        self,
        draft: CanonicalProductDraft,
    ) -> CanonicalProduct | None:
        """
        Draft와 동일한 CanonicalProduct를 검색한다.

        존재하지 않으면 None을 반환한다.
        """
        if not isinstance(
            draft,
            CanonicalProductDraft,
        ):
            raise TypeError(
                "draft는 CanonicalProductDraft 객체여야 합니다."
            )

        target_key = self._build_identity_key_from_draft(
            draft
        )

        for product in self._repository.list_all():
            product_key = (
                self._build_identity_key_from_product(
                    product
                )
            )

            if product_key == target_key:
                return product

        return None

    def create(
        self,
        draft: CanonicalProductDraft,
    ) -> CanonicalProduct:
        """
        Draft를 기반으로 새로운 CanonicalProduct를 생성하고 저장한다.

        기존 상품 검색은 수행하지 않는다.
        중복 방지가 필요한 일반적인 흐름에서는 find_or_create를 사용한다.
        """
        if not isinstance(
            draft,
            CanonicalProductDraft,
        ):
            raise TypeError(
                "draft는 CanonicalProductDraft 객체여야 합니다."
            )

        with self._lock:
            display_id = self._id_generator.generate()

            product = CanonicalProduct(
                display_id=display_id,
                brand=draft.brand,
                model=draft.model,
                category=draft.category,
                capacity=draft.capacity,
                color=draft.color,
                size=draft.size,
                edition=draft.edition,
                condition=draft.condition,
                attributes=draft.attributes,
            )

            return self._repository.create(
                product
            )

    def find_or_create(
        self,
        draft: CanonicalProductDraft,
    ) -> CatalogResult:
        """
        기존 동일 상품을 반환하거나 새로운 CanonicalProduct를 생성한다.

        RLock 내부에서 검색과 생성을 함께 수행하므로
        하나의 CatalogManager 인스턴스를 여러 스레드가 사용해도
        동일 상품이 중복 생성되지 않는다.
        """
        if not isinstance(
            draft,
            CanonicalProductDraft,
        ):
            raise TypeError(
                "draft는 CanonicalProductDraft 객체여야 합니다."
            )

        with self._lock:
            existing_product = self.find(
                draft
            )

            if existing_product is not None:
                return CatalogResult(
                    product=existing_product,
                    created=False,
                )

            created_product = self.create(
                draft
            )

            return CatalogResult(
                product=created_product,
                created=True,
            )