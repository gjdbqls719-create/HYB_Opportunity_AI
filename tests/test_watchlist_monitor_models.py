from __future__ import annotations

import pytest

from app.application.watchlist import (
    MonitorItemResult,
    MonitorStatus,
    WatchListMonitorResult,
)


def make_result(
    status: MonitorStatus,
    **overrides,
) -> MonitorItemResult:
    values = {
        "watch_id": "watch-001",
        "marketplace": "ebay",
        "item_id": "item-001",
        "status": status,
        "previous_price": None,
        "current_price": None,
        "currency": "",
        "change_count": 0,
        "error_message": "",
    }

    if status is MonitorStatus.UPDATED:
        values.update(
            previous_price=500.0,
            current_price=450.0,
            currency="USD",
            change_count=1,
        )
    elif status is MonitorStatus.UNCHANGED:
        values.update(
            previous_price=450.0,
            current_price=450.0,
            currency="USD",
        )
    elif status is MonitorStatus.FAILED:
        values.update(error_message="network timeout")

    values.update(overrides)
    return MonitorItemResult(**values)


def test_monitor_status_values_are_stable() -> None:
    assert MonitorStatus.UPDATED == "updated"
    assert MonitorStatus.UNCHANGED == "unchanged"
    assert MonitorStatus.NOT_FOUND == "not_found"
    assert MonitorStatus.FAILED == "failed"


def test_item_result_normalizes_text_fields() -> None:
    result = make_result(
        MonitorStatus.UPDATED,
        watch_id="  watch-001  ",
        marketplace="  EBAY  ",
        item_id="  item-001  ",
        currency=" usd ",
    )

    assert result.watch_id == "watch-001"
    assert result.marketplace == "ebay"
    assert result.item_id == "item-001"
    assert result.currency == "USD"


def test_updated_result_reports_success_and_changes() -> None:
    result = make_result(MonitorStatus.UPDATED)

    assert result.is_successful is True
    assert result.has_changes is True


def test_unchanged_result_reports_success_without_changes() -> None:
    result = make_result(MonitorStatus.UNCHANGED)

    assert result.is_successful is True
    assert result.has_changes is False


def test_not_found_result_is_not_successful() -> None:
    result = make_result(MonitorStatus.NOT_FOUND)

    assert result.is_successful is False
    assert result.has_changes is False


def test_failed_result_requires_error_message() -> None:
    with pytest.raises(ValueError, match="error_message"):
        make_result(
            MonitorStatus.FAILED,
            error_message="   ",
        )


def test_non_failed_result_rejects_error_message() -> None:
    with pytest.raises(ValueError, match="error_message"):
        make_result(
            MonitorStatus.NOT_FOUND,
            error_message="unexpected",
        )


def test_completed_result_requires_current_price() -> None:
    with pytest.raises(ValueError, match="current_price"):
        make_result(
            MonitorStatus.UNCHANGED,
            current_price=None,
        )


def test_completed_result_requires_currency() -> None:
    with pytest.raises(ValueError, match="currency"):
        make_result(
            MonitorStatus.UNCHANGED,
            currency="   ",
        )


def test_updated_result_requires_positive_change_count() -> None:
    with pytest.raises(ValueError, match="change_count"):
        make_result(
            MonitorStatus.UPDATED,
            change_count=0,
        )


def test_non_updated_result_rejects_change_count() -> None:
    with pytest.raises(ValueError, match="change_count"):
        make_result(
            MonitorStatus.UNCHANGED,
            change_count=1,
        )


@pytest.mark.parametrize(
    "field_name,value,error_type",
    [
        ("previous_price", -1.0, ValueError),
        ("current_price", float("inf"), ValueError),
        ("current_price", True, TypeError),
    ],
)
def test_item_result_rejects_invalid_prices(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type, match=field_name):
        make_result(
            MonitorStatus.UNCHANGED,
            **{field_name: value},
        )


def test_batch_result_converts_items_to_tuple() -> None:
    source = [make_result(MonitorStatus.UNCHANGED)]

    result = WatchListMonitorResult(items=source)

    assert isinstance(result.items, tuple)
    assert result.items == tuple(source)


def test_batch_result_rejects_invalid_item() -> None:
    with pytest.raises(TypeError, match="MonitorItemResult"):
        WatchListMonitorResult(items=(object(),))


def test_batch_result_aggregates_all_statuses() -> None:
    result = WatchListMonitorResult(
        items=(
            make_result(MonitorStatus.UPDATED),
            make_result(
                MonitorStatus.UPDATED,
                watch_id="watch-002",
                item_id="item-002",
                change_count=2,
            ),
            make_result(
                MonitorStatus.UNCHANGED,
                watch_id="watch-003",
                item_id="item-003",
            ),
            make_result(
                MonitorStatus.NOT_FOUND,
                watch_id="watch-004",
                item_id="item-004",
            ),
            make_result(
                MonitorStatus.FAILED,
                watch_id="watch-005",
                item_id="item-005",
            ),
        )
    )

    assert result.total_count == 5
    assert result.successful_count == 3
    assert result.updated_count == 2
    assert result.unchanged_count == 1
    assert result.not_found_count == 1
    assert result.failed_count == 1
    assert result.change_count == 3
    assert result.has_changes is True
    assert result.has_failures is True


def test_empty_batch_result_has_zero_counts() -> None:
    result = WatchListMonitorResult(items=())

    assert result.total_count == 0
    assert result.successful_count == 0
    assert result.updated_count == 0
    assert result.unchanged_count == 0
    assert result.not_found_count == 0
    assert result.failed_count == 0
    assert result.change_count == 0
    assert result.has_changes is False
    assert result.has_failures is False
