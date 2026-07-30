from __future__ import annotations

from io import StringIO

from app.application.watchlist import (
    MonitorItemResult,
    MonitorStatus,
    WatchListMonitorResult,
)
from app.cli import run_cli


class FakeMonitor:
    def __init__(
        self,
        result: WatchListMonitorResult,
    ) -> None:
        self.result = result
        self.execute_count = 0

    def execute(self) -> WatchListMonitorResult:
        self.execute_count += 1
        return self.result


def make_result() -> WatchListMonitorResult:
    return WatchListMonitorResult(
        items=(
            MonitorItemResult(
                watch_id="updated",
                marketplace="ebay",
                item_id="item-1",
                status=MonitorStatus.UPDATED,
                previous_price=100.0,
                current_price=80.0,
                currency="USD",
                change_count=1,
            ),
            MonitorItemResult(
                watch_id="unchanged",
                marketplace="amazon",
                item_id="item-2",
                status=MonitorStatus.UNCHANGED,
                previous_price=100.0,
                current_price=100.0,
                currency="USD",
            ),
            MonitorItemResult(
                watch_id="missing",
                marketplace="ebay",
                item_id="item-3",
                status=MonitorStatus.NOT_FOUND,
            ),
            MonitorItemResult(
                watch_id="failed",
                marketplace="amazon",
                item_id="item-4",
                status=MonitorStatus.FAILED,
                error_message="lookup failed",
            ),
        )
    )


def test_watch_monitor_cli_executes_factory_and_renders_summary(
    monkeypatch,
    tmp_path,
) -> None:
    database_path = tmp_path / "watch-monitor.db"
    monitor = FakeMonitor(make_result())
    captured: dict[str, object] = {}

    def fake_create_watchlist_monitor(path):
        captured["database_path"] = path
        return monitor

    monkeypatch.setattr(
        "app.cli.create_watchlist_monitor",
        fake_create_watchlist_monitor,
    )

    output = StringIO()
    errors = StringIO()
    exit_code = run_cli(
        [
            "--watch-monitor",
            "--db",
            str(database_path),
        ],
        input_stream=StringIO(""),
        output=output,
        error_output=errors,
    )

    assert exit_code == 0
    assert captured["database_path"] == str(database_path)
    assert monitor.execute_count == 1
    assert output.getvalue() == (
        "\nWatchList Monitor\n"
        f"{'=' * 64}\n"
        "Total: 4\n"
        "Updated: 1\n"
        "Unchanged: 1\n"
        "Failed: 1\n"
        "Not Found: 1\n"
    )
    assert errors.getvalue() == ""


def test_watch_monitor_cli_runs_with_isolated_empty_database(
    tmp_path,
) -> None:
    output = StringIO()
    errors = StringIO()

    exit_code = run_cli(
        [
            "--watch-monitor",
            "--db",
            str(tmp_path / "empty-watchlist.db"),
        ],
        output=output,
        error_output=errors,
    )

    assert exit_code == 0
    assert "Total: 0" in output.getvalue()
    assert "Updated: 0" in output.getvalue()
    assert "Unchanged: 0" in output.getvalue()
    assert "Failed: 0" in output.getvalue()
    assert "Not Found: 0" in output.getvalue()
    assert errors.getvalue() == ""
