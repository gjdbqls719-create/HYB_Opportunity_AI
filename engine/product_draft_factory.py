from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, Mapping

from app.models import Product
from engine.catalog_manager import CanonicalProductDraft
from engine.product_attribute_extractor import (
    extract_attributes_from_product,
)
from engine.product_attributes import ProductAttributes


ProductAttributeExtractor = Callable[
    [Product],
    ProductAttributes,
]


class ProductDraftFactory:
    """
    Marketplace 공통 Product를 CanonicalProductDraft로 변환한다.

    책임:

    - Product에서 ProductAttributes 추출
    - ProductAttributes를 CanonicalProductDraft로 변환
    - Canonical Catalog에 필요한 의미 있는 확장 속성 구성
    - Strong Identity와 Weak Identity를 구분
    - 식별력이 부족한 상품의 normalized_title 유지

    다음 책임은 수행하지 않는다:

    - Canonical ID 생성
    - Repository 저장
    - 기존 CanonicalProduct 검색
    - 상품 동일성 최종 판단
    """

    STRONG_IDENTITY_FIELDS: ClassVar[
        tuple[str, ...]
    ] = (
        "brand",
        "model_number",
        "capacity",
        "edition",
    )

    WEAK_IDENTITY_FIELDS: ClassVar[
        tuple[str, ...]
    ] = (
        "category",
        "condition",
        "color",
        "size",
    )

    def __init__(
        self,
        *,
        attribute_extractor: ProductAttributeExtractor = (
            extract_attributes_from_product
        ),
    ) -> None:
        if not callable(attribute_extractor):
            raise TypeError(
                "attribute_extractor는 호출 가능한 객체여야 합니다."
            )

        self._attribute_extractor = attribute_extractor

    @property
    def attribute_extractor(
        self,
    ) -> ProductAttributeExtractor:
        """
        Factory가 사용하는 상품 속성 추출기를 반환한다.
        """
        return self._attribute_extractor

    @classmethod
    def _has_strong_identity(
        cls,
        attributes: ProductAttributes,
    ) -> bool:
        """
        강한 상품 식별 정보가 하나 이상 존재하는지 반환한다.

        Strong Identity:

        - brand
        - model_number
        - capacity
        - edition

        Strong Identity가 존재하면 구조화된 속성만으로도
        최소 수준의 상품 정체성을 구성할 수 있다고 판단한다.
        """
        if not isinstance(
            attributes,
            ProductAttributes,
        ):
            raise TypeError(
                "attributes는 ProductAttributes 객체여야 합니다."
            )

        return any(
            getattr(attributes, field_name)
            for field_name
            in cls.STRONG_IDENTITY_FIELDS
        )

    @classmethod
    def _has_weak_identity(
        cls,
        attributes: ProductAttributes,
    ) -> bool:
        """
        약한 상품 식별 정보가 하나 이상 존재하는지 반환한다.

        Weak Identity:

        - category
        - condition
        - color
        - size

        Weak Identity는 상품의 상태나 분류를 설명하지만,
        단독으로는 특정 상품을 안전하게 식별하기 어렵다.
        """
        if not isinstance(
            attributes,
            ProductAttributes,
        ):
            raise TypeError(
                "attributes는 ProductAttributes 객체여야 합니다."
            )

        return any(
            getattr(attributes, field_name)
            for field_name
            in cls.WEAK_IDENTITY_FIELDS
        )

    @classmethod
    def _has_structured_identity(
        cls,
        attributes: ProductAttributes,
    ) -> bool:
        """
        이전 내부 API와의 호환성을 위해 유지한다.

        이제 구조화된 식별 정보의 존재 여부는
        Strong Identity 기준으로 판단한다.

        category, condition, color, size만 존재하는 경우에는
        False를 반환한다.
        """
        return cls._has_strong_identity(
            attributes
        )

    @classmethod
    def _should_preserve_normalized_title(
        cls,
        attributes: ProductAttributes,
    ) -> bool:
        """
        normalized_title을 확장 속성에 유지할지 판단한다.

        Strong Identity가 없으면 제목을 유지한다.

        Weak Identity만 있는 상품은 서로 다른 상품이 같은
        category와 condition을 공유할 가능성이 높으므로,
        과도한 Canonical 병합을 방지하기 위해 정규화 제목을
        상품 정체성의 일부로 사용한다.
        """
        return not cls._has_strong_identity(
            attributes
        )

    @classmethod
    def _build_extended_attributes(
        cls,
        attributes: ProductAttributes,
    ) -> Mapping[str, str]:
        """
        CanonicalProductDraft에 저장할 확장 속성을 구성한다.

        normalized_title:
            Strong Identity가 없을 때 상품의 최후 식별 정보로
            저장한다.

        quantity:
            묶음 수량이 존재할 때 저장한다.

        is_bundle / is_accessory:
            True인 경우에만 저장한다.

        tokens:
            검색과 분석을 위한 파생 정보이므로 Canonical 상품
            정체성에는 포함하지 않는다.
        """
        if not isinstance(
            attributes,
            ProductAttributes,
        ):
            raise TypeError(
                "attributes는 ProductAttributes 객체여야 합니다."
            )

        extended: dict[str, str] = {}

        if cls._should_preserve_normalized_title(
            attributes
        ):
            extended[
                "normalized_title"
            ] = attributes.normalized_title

        if attributes.quantity is not None:
            extended["quantity"] = str(
                attributes.quantity
            )

        if attributes.is_bundle:
            extended["is_bundle"] = "true"

        if attributes.is_accessory:
            extended["is_accessory"] = "true"

        return extended

    def from_attributes(
        self,
        attributes: ProductAttributes,
    ) -> CanonicalProductDraft:
        """
        ProductAttributes를 CanonicalProductDraft로 변환한다.
        """
        if not isinstance(
            attributes,
            ProductAttributes,
        ):
            raise TypeError(
                "attributes는 ProductAttributes 객체여야 합니다."
            )

        return CanonicalProductDraft(
            brand=attributes.brand,
            model=attributes.model_number,
            category=attributes.category,
            capacity=attributes.capacity,
            color=attributes.color,
            size=attributes.size,
            edition=attributes.edition,
            condition=attributes.condition,
            attributes=self._build_extended_attributes(
                attributes
            ),
        )

    def from_product(
        self,
        product: Product,
    ) -> CanonicalProductDraft:
        """
        공통 Product에서 속성을 추출하고
        CanonicalProductDraft를 생성한다.
        """
        if not isinstance(product, Product):
            raise TypeError(
                "product는 Product 객체여야 합니다."
            )

        extracted_attributes = (
            self._attribute_extractor(
                product
            )
        )

        if not isinstance(
            extracted_attributes,
            ProductAttributes,
        ):
            raise TypeError(
                "attribute_extractor는 ProductAttributes를 "
                "반환해야 합니다."
            )

        return self.from_attributes(
            extracted_attributes
        )