from __future__ import annotations

from io import StringIO

from app.cli import run_cli


def test_cli_runs_full_search_flow(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_find_best_opportunities(
        **kwargs,
    ):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        "app.cli.find_best_opportunities",
        fake_find_best_opportunities,
    )

    output = StringIO()
    errors = StringIO()

    exit_code = run_cli(
        [
            "gaming mouse",
            "--limit",
            "3",
            "--top",
            "2",
            "--no-save",
        ],
        output=output,
        error_output=errors,
    )

    rendered = output.getvalue()

    assert exit_code == 0
    assert captured["query"] == "gaming mouse"
    assert captured["limit"] == 3

    assert "검색어: gaming mouse" in rendered
    assert "분석 결과: 0개 그룹" in rendered
    assert "표시 결과: 0개" in rendered
    assert "No dashboard results." in rendered

    assert errors.getvalue() == ""


def test_cli_reads_query_interactively(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.cli.find_best_opportunities",
        lambda **kwargs: [],
    )

    output = StringIO()

    exit_code = run_cli(
        ["--no-save"],
        input_stream=StringIO(
            "keyboard\n"
        ),
        output=output,
        error_output=StringIO(),
    )

    rendered = output.getvalue()

    assert exit_code == 0
    assert "검색어: keyboard" in rendered
    assert "No dashboard results." in rendered


def test_cli_rejects_empty_query() -> None:
    errors = StringIO()

    exit_code = run_cli(
        ["--no-save"],
        input_stream=StringIO("\n"),
        output=StringIO(),
        error_output=errors,
    )

    assert exit_code == 1
    assert (
        "검색어를 입력해야 합니다."
        in errors.getvalue()
    )


def test_cli_prints_marketplace_warning(
    monkeypatch,
) -> None:
    def fake_find_best_opportunities(
        **kwargs,
    ):
        kwargs["search_error_handler"](
            "ebay",
            RuntimeError(
                "API key missing"
            ),
        )
        return []

    monkeypatch.setattr(
        "app.cli.find_best_opportunities",
        fake_find_best_opportunities,
    )

    output = StringIO()
    errors = StringIO()

    exit_code = run_cli(
        [
            "gaming mouse",
            "--no-save",
        ],
        output=output,
        error_output=errors,
    )

    rendered = output.getvalue()
    error_text = errors.getvalue()

    assert exit_code == 0

    assert "검색어: gaming mouse" in rendered
    assert "분석 결과: 0개 그룹" in rendered
    assert "No dashboard results." in rendered

    assert (
        "경고: ebay 검색 실패: "
        "API key missing"
        in error_text
    )


def test_cli_history_mode_does_not_search(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_search(
        **kwargs,
    ):
        raise AssertionError(
            "검색이 호출되면 안 됩니다."
        )

    monkeypatch.setattr(
        "app.cli.find_best_opportunities",
        fail_search,
    )

    output = StringIO()

    exit_code = run_cli(
        [
            "--history",
            "--db",
            str(
                tmp_path
                / "history.db"
            ),
        ],
        output=output,
        error_output=StringIO(),
    )

    rendered = output.getvalue()

    assert exit_code == 0
    assert (
        "저장된 최근 기회 분석"
        in rendered
    )
    assert (
        "저장된 분석 결과가 없습니다."
        in rendered
    )