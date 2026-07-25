from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from engine.canonical_id_generator import (
    CanonicalIdGenerator,
    InMemoryCanonicalIdGenerator,
)


def test_generator_implements_interface() -> None:
    generator = InMemoryCanonicalIdGenerator()

    assert isinstance(
        generator,
        CanonicalIdGenerator,
    )


def test_default_generator_starts_at_one() -> None:
    generator = InMemoryCanonicalIdGenerator()

    assert generator.generate() == "CP-000001"


def test_generator_increments_sequence() -> None:
    generator = InMemoryCanonicalIdGenerator()

    assert generator.generate() == "CP-000001"
    assert generator.generate() == "CP-000002"
    assert generator.generate() == "CP-000003"


def test_custom_start_is_supported() -> None:
    generator = InMemoryCanonicalIdGenerator(
        start=25
    )

    assert generator.generate() == "CP-000025"
    assert generator.generate() == "CP-000026"


def test_custom_prefix_is_supported() -> None:
    generator = InMemoryCanonicalIdGenerator(
        prefix="PRODUCT"
    )

    assert generator.generate() == (
        "PRODUCT-000001"
    )


def test_custom_width_is_supported() -> None:
    generator = InMemoryCanonicalIdGenerator(
        width=8
    )

    assert generator.generate() == (
        "CP-00000001"
    )


def test_sequence_can_exceed_minimum_width() -> None:
    generator = InMemoryCanonicalIdGenerator(
        start=999999,
        width=6,
    )

    assert generator.generate() == "CP-999999"
    assert generator.generate() == "CP-1000000"


def test_properties_return_configuration() -> None:
    generator = InMemoryCanonicalIdGenerator(
        prefix="ITEM",
        start=10,
        width=8,
    )

    assert generator.prefix == "ITEM"
    assert generator.width == 8
    assert generator.next_sequence == 10


def test_next_sequence_does_not_consume_id() -> None:
    generator = InMemoryCanonicalIdGenerator()

    assert generator.next_sequence == 1
    assert generator.next_sequence == 1
    assert generator.generate() == "CP-000001"
    assert generator.next_sequence == 2


@pytest.mark.parametrize(
    "invalid_prefix",
    [
        "",
        "   ",
        "cp",
        "CP-",
        "C P",
        "1CP",
        "CP_",
    ],
)
def test_invalid_prefix_raises_value_error(
    invalid_prefix: str,
) -> None:
    with pytest.raises(ValueError):
        InMemoryCanonicalIdGenerator(
            prefix=invalid_prefix
        )


@pytest.mark.parametrize(
    "invalid_prefix",
    [
        None,
        123,
        True,
    ],
)
def test_non_string_prefix_raises_type_error(
    invalid_prefix: object,
) -> None:
    with pytest.raises(TypeError):
        InMemoryCanonicalIdGenerator(
            prefix=invalid_prefix,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_start",
    [
        0,
        -1,
    ],
)
def test_non_positive_start_raises_value_error(
    invalid_start: int,
) -> None:
    with pytest.raises(ValueError):
        InMemoryCanonicalIdGenerator(
            start=invalid_start
        )


@pytest.mark.parametrize(
    "invalid_start",
    [
        1.5,
        "1",
        True,
        None,
    ],
)
def test_non_integer_start_raises_type_error(
    invalid_start: object,
) -> None:
    with pytest.raises(TypeError):
        InMemoryCanonicalIdGenerator(
            start=invalid_start,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_width",
    [
        0,
        -1,
    ],
)
def test_non_positive_width_raises_value_error(
    invalid_width: int,
) -> None:
    with pytest.raises(ValueError):
        InMemoryCanonicalIdGenerator(
            width=invalid_width
        )


@pytest.mark.parametrize(
    "invalid_width",
    [
        1.5,
        "6",
        True,
        None,
    ],
)
def test_non_integer_width_raises_type_error(
    invalid_width: object,
) -> None:
    with pytest.raises(TypeError):
        InMemoryCanonicalIdGenerator(
            width=invalid_width,  # type: ignore[arg-type]
        )


def test_synchronize_advances_sequence() -> None:
    generator = InMemoryCanonicalIdGenerator()

    generator.synchronize(
        [
            "CP-000001",
            "CP-000005",
            "CP-000012",
        ]
    )

    assert generator.generate() == "CP-000013"


def test_synchronize_ignores_unrelated_ids() -> None:
    generator = InMemoryCanonicalIdGenerator()

    generator.synchronize(
        [
            "PRODUCT-000100",
            "invalid",
            "CP-00001",
            "cp-000500",
        ]
    )

    assert generator.generate() == "CP-000001"


def test_synchronize_does_not_move_sequence_backward() -> None:
    generator = InMemoryCanonicalIdGenerator(
        start=100
    )

    generator.synchronize(
        [
            "CP-000001",
            "CP-000050",
        ]
    )

    assert generator.generate() == "CP-000100"


def test_synchronize_accepts_generator_expression() -> None:
    generator = InMemoryCanonicalIdGenerator()

    existing_ids = (
        f"CP-{number:06d}"
        for number in range(1, 11)
    )

    generator.synchronize(
        existing_ids
    )

    assert generator.generate() == "CP-000011"


def test_synchronize_rejects_single_string() -> None:
    generator = InMemoryCanonicalIdGenerator()

    with pytest.raises(TypeError):
        generator.synchronize(
            "CP-000100"
        )


def test_synchronize_rejects_non_string_items() -> None:
    generator = InMemoryCanonicalIdGenerator()

    with pytest.raises(TypeError):
        generator.synchronize(
            [
                "CP-000001",
                2,
            ]  # type: ignore[list-item]
        )


def test_concurrent_generation_produces_unique_ids() -> None:
    generator = InMemoryCanonicalIdGenerator()

    with ThreadPoolExecutor(
        max_workers=10
    ) as executor:
        generated_ids = list(
            executor.map(
                lambda _: generator.generate(),
                range(100),
            )
        )

    assert len(generated_ids) == 100
    assert len(set(generated_ids)) == 100
    assert generator.next_sequence == 101
    assert min(generated_ids) == "CP-000001"
    assert max(generated_ids) == "CP-000100"