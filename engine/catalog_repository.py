from __future__ import annotations

from abc import ABC, abstractmethod
from threading import RLock
from typing import Iterable
from uuid import UUID

from app.models.canonical_product import CanonicalProduct


class CatalogRepositoryError(Exception):
    """
    Catalog Repository에서 발생하는 기본 예외.
    """


class DuplicateCanonicalProductError(
    CatalogRepositoryError
):
    """
    동일한 내부 ID 또는 display_id를 가진 상품이 이미 존재할 때 발생한다.
    """


class CanonicalProductNotFoundError(
    CatalogRepositoryError
):
    """
    요청한 CanonicalProduct를 찾을 수 없을 때 발생한다.
    """


class CatalogRepository(ABC):
    """
    CanonicalProduct 저장소 인터페이스.

    Catalog Manager는 구체적인 저장 방식에 직접 의존하지 않고
    이 인터페이스를 통해 상품을 저장하고 조회한다.
    """

    @abstractmethod
    def create(
        self,
        product: CanonicalProduct,
    ) -> CanonicalProduct:
        """
        새로운 CanonicalProduct를 저장한다.

        동일한 내부 ID 또는 display_id가 이미 존재하면
        DuplicateCanonicalProductError를 발생시킨다.
        """
        raise NotImplementedError

    @abstractmethod
    def create_many(
        self,
        products: Iterable[CanonicalProduct],
    ) -> tuple[CanonicalProduct, ...]:
        """
        여러 CanonicalProduct를 한 번에 저장한다.

        하나라도 중복되거나 잘못된 값이 있으면 전체 저장을 취소한다.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_id(
        self,
        product_id: UUID,
    ) -> CanonicalProduct:
        """
        내부 UUID로 CanonicalProduct를 조회한다.

        존재하지 않으면 CanonicalProductNotFoundError를 발생시킨다.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_display_id(
        self,
        display_id: str,
    ) -> CanonicalProduct:
        """
        표시용 ID로 CanonicalProduct를 조회한다.

        존재하지 않으면 CanonicalProductNotFoundError를 발생시킨다.
        """
        raise NotImplementedError

    @abstractmethod
    def find_by_id(
        self,
        product_id: UUID,
    ) -> CanonicalProduct | None:
        """
        내부 UUID로 상품을 조회한다.

        존재하지 않으면 None을 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def find_by_display_id(
        self,
        display_id: str,
    ) -> CanonicalProduct | None:
        """
        표시용 ID로 상품을 조회한다.

        존재하지 않으면 None을 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def exists_by_id(
        self,
        product_id: UUID,
    ) -> bool:
        """
        내부 UUID를 가진 상품이 존재하는지 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def exists_by_display_id(
        self,
        display_id: str,
    ) -> bool:
        """
        표시용 ID를 가진 상품이 존재하는지 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def list_all(
        self,
    ) -> tuple[CanonicalProduct, ...]:
        """
        저장된 모든 CanonicalProduct를 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def count(
        self,
    ) -> int:
        """
        저장된 상품 수를 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        product_id: UUID,
    ) -> CanonicalProduct:
        """
        내부 UUID에 해당하는 상품을 삭제하고 삭제된 상품을 반환한다.

        존재하지 않으면 CanonicalProductNotFoundError를 발생시킨다.
        """
        raise NotImplementedError

    @abstractmethod
    def clear(
        self,
    ) -> None:
        """
        저장된 모든 상품을 삭제한다.
        """
        raise NotImplementedError


class InMemoryCatalogRepository(
    CatalogRepository
):
    """
    메모리에 CanonicalProduct를 저장하는 Repository 구현체.

    내부 UUID와 display_id를 각각 인덱스로 관리한다.

    RLock을 사용하므로 하나의 프로세스 안에서 여러 스레드가
    동시에 접근해도 저장소 내부 상태가 손상되지 않는다.

    프로세스가 종료되면 저장된 데이터는 사라지므로 현재는
    개발 및 테스트 용도로 사용한다.
    """

    def __init__(self) -> None:
        self._products_by_id: dict[
            UUID,
            CanonicalProduct,
        ] = {}

        self._product_ids_by_display_id: dict[
            str,
            UUID,
        ] = {}

        self._lock = RLock()

    @staticmethod
    def _validate_product(
        product: CanonicalProduct,
    ) -> CanonicalProduct:
        if not isinstance(
            product,
            CanonicalProduct,
        ):
            raise TypeError(
                "product는 CanonicalProduct 객체여야 합니다."
            )

        return product

    @staticmethod
    def _validate_product_id(
        product_id: UUID,
    ) -> UUID:
        if not isinstance(product_id, UUID):
            raise TypeError(
                "product_id는 UUID 객체여야 합니다."
            )

        return product_id

    @staticmethod
    def _validate_display_id(
        display_id: str,
    ) -> str:
        if not isinstance(display_id, str):
            raise TypeError(
                "display_id는 문자열이어야 합니다."
            )

        normalized = display_id.strip()

        if not normalized:
            raise ValueError(
                "display_id는 비어 있을 수 없습니다."
            )

        return normalized

    def _ensure_product_does_not_exist(
        self,
        product: CanonicalProduct,
    ) -> None:
        if product.id in self._products_by_id:
            raise DuplicateCanonicalProductError(
                f"내부 ID가 이미 존재합니다: {product.id}"
            )

        if (
            product.display_id
            in self._product_ids_by_display_id
        ):
            raise DuplicateCanonicalProductError(
                "display_id가 이미 존재합니다: "
                f"{product.display_id}"
            )

    def create(
        self,
        product: CanonicalProduct,
    ) -> CanonicalProduct:
        validated_product = self._validate_product(
            product
        )

        with self._lock:
            self._ensure_product_does_not_exist(
                validated_product
            )

            self._products_by_id[
                validated_product.id
            ] = validated_product

            self._product_ids_by_display_id[
                validated_product.display_id
            ] = validated_product.id

            return validated_product

    def create_many(
        self,
        products: Iterable[CanonicalProduct],
    ) -> tuple[CanonicalProduct, ...]:
        if isinstance(products, (str, bytes)):
            raise TypeError(
                "products는 CanonicalProduct 컬렉션이어야 합니다."
            )

        try:
            product_list = list(products)
        except TypeError as error:
            raise TypeError(
                "products는 반복 가능한 객체여야 합니다."
            ) from error

        validated_products = tuple(
            self._validate_product(product)
            for product in product_list
        )

        with self._lock:
            incoming_ids: set[UUID] = set()
            incoming_display_ids: set[str] = set()

            for product in validated_products:
                self._ensure_product_does_not_exist(
                    product
                )

                if product.id in incoming_ids:
                    raise DuplicateCanonicalProductError(
                        "저장 요청 내부에 중복된 ID가 있습니다: "
                        f"{product.id}"
                    )

                if (
                    product.display_id
                    in incoming_display_ids
                ):
                    raise DuplicateCanonicalProductError(
                        "저장 요청 내부에 중복된 display_id가 있습니다: "
                        f"{product.display_id}"
                    )

                incoming_ids.add(product.id)
                incoming_display_ids.add(
                    product.display_id
                )

            for product in validated_products:
                self._products_by_id[
                    product.id
                ] = product

                self._product_ids_by_display_id[
                    product.display_id
                ] = product.id

            return validated_products

    def get_by_id(
        self,
        product_id: UUID,
    ) -> CanonicalProduct:
        validated_id = self._validate_product_id(
            product_id
        )

        with self._lock:
            product = self._products_by_id.get(
                validated_id
            )

            if product is None:
                raise CanonicalProductNotFoundError(
                    "CanonicalProduct를 찾을 수 없습니다: "
                    f"{validated_id}"
                )

            return product

    def get_by_display_id(
        self,
        display_id: str,
    ) -> CanonicalProduct:
        normalized_display_id = (
            self._validate_display_id(
                display_id
            )
        )

        with self._lock:
            product_id = (
                self._product_ids_by_display_id.get(
                    normalized_display_id
                )
            )

            if product_id is None:
                raise CanonicalProductNotFoundError(
                    "CanonicalProduct를 찾을 수 없습니다: "
                    f"{normalized_display_id}"
                )

            return self._products_by_id[
                product_id
            ]

    def find_by_id(
        self,
        product_id: UUID,
    ) -> CanonicalProduct | None:
        validated_id = self._validate_product_id(
            product_id
        )

        with self._lock:
            return self._products_by_id.get(
                validated_id
            )

    def find_by_display_id(
        self,
        display_id: str,
    ) -> CanonicalProduct | None:
        normalized_display_id = (
            self._validate_display_id(
                display_id
            )
        )

        with self._lock:
            product_id = (
                self._product_ids_by_display_id.get(
                    normalized_display_id
                )
            )

            if product_id is None:
                return None

            return self._products_by_id.get(
                product_id
            )

    def exists_by_id(
        self,
        product_id: UUID,
    ) -> bool:
        validated_id = self._validate_product_id(
            product_id
        )

        with self._lock:
            return (
                validated_id
                in self._products_by_id
            )

    def exists_by_display_id(
        self,
        display_id: str,
    ) -> bool:
        normalized_display_id = (
            self._validate_display_id(
                display_id
            )
        )

        with self._lock:
            return (
                normalized_display_id
                in self._product_ids_by_display_id
            )

    def list_all(
        self,
    ) -> tuple[CanonicalProduct, ...]:
        with self._lock:
            return tuple(
                self._products_by_id.values()
            )

    def count(
        self,
    ) -> int:
        with self._lock:
            return len(
                self._products_by_id
            )

    def delete(
        self,
        product_id: UUID,
    ) -> CanonicalProduct:
        validated_id = self._validate_product_id(
            product_id
        )

        with self._lock:
            product = self._products_by_id.pop(
                validated_id,
                None,
            )

            if product is None:
                raise CanonicalProductNotFoundError(
                    "삭제할 CanonicalProduct를 찾을 수 없습니다: "
                    f"{validated_id}"
                )

            self._product_ids_by_display_id.pop(
                product.display_id,
                None,
            )

            return product

    def clear(
        self,
    ) -> None:
        with self._lock:
            self._products_by_id.clear()
            self._product_ids_by_display_id.clear()