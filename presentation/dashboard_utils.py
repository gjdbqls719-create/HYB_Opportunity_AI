from __future__ import annotations

from typing import Any


def _analysis_float(
    analysis: dict[str, Any],
    *keys: str,
) -> float:
    """
    분석 결과 딕셔너리에서 첫 번째로 발견되는
    유효한 값을 float로 변환한다.
    """
    for key in keys:
        if key not in analysis:
            continue

        value = analysis[key]

        if value is not None:
            return _to_float(value)

    return 0.0


def _first_text_attribute(
    target: object,
    *attribute_names: str,
) -> str:
    """
    객체의 여러 속성 중 첫 번째로 발견되는
    비어 있지 않은 문자열 값을 반환한다.
    """
    for attribute_name in attribute_names:
        value = _to_text(
            getattr(
                target,
                attribute_name,
                "",
            )
        )

        if value:
            return value

    return ""


def _to_text(
    value: object,
) -> str:
    """
    값을 안전하게 문자열로 변환한다.

    None은 빈 문자열로 처리하며,
    문자열 앞뒤 공백을 제거한다.
    """
    if value is None:
        return ""

    return str(value).strip()


def _to_float(
    value: object,
) -> float:
    """
    숫자 또는 숫자 형태 문자열을
    안전하게 float로 변환한다.

    쉼표와 퍼센트 기호가 포함된 문자열도 처리한다.
    변환할 수 없는 값은 0.0을 반환한다.
    """
    if value is None:
        return 0.0

    if isinstance(value, str):
        cleaned = (
            value.strip()
            .replace(",", "")
            .replace("%", "")
        )

        if not cleaned:
            return 0.0

        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_text_tuple(
    values: object,
) -> tuple[str, ...]:
    """
    단일 값 또는 반복 가능한 값을
    중복 없는 문자열 튜플로 변환한다.
    """
    if values is None:
        return ()

    if isinstance(values, str):
        cleaned = values.strip()

        if not cleaned:
            return ()

        return (cleaned,)

    try:
        items = tuple(values)
    except TypeError:
        cleaned = _to_text(values)

        if not cleaned:
            return ()

        return (cleaned,)

    cleaned_items: list[str] = []

    for item in items:
        cleaned = _to_text(item)

        if (
            cleaned
            and cleaned not in cleaned_items
        ):
            cleaned_items.append(cleaned)

    return tuple(cleaned_items)