"""`sec-agent report sync` writes the README block and the bullets from runs.csv."""

from pathlib import Path

import pytest
from report_kit import bullet_rows, run

from sec_agent.cli import main
from sec_agent.runs import append_run


def _setup(tmp: Path) -> tuple[Path, Path, Path]:
    runs = tmp / "runs.csv"
    for row in bullet_rows():
        append_run(runs, row)
    readme = tmp / "README.md"
    readme.write_text("# T\n<!-- results:start -->\n<!-- results:end -->\n", "utf-8")
    return runs, readme, tmp / "bullets.md"


def _args(runs: Path, readme: Path, bullets: Path, *extra: str) -> list[str]:
    return [
        "report",
        "sync",
        "--runs",
        str(runs),
        "--readme",
        str(readme),
        "--bullets",
        str(bullets),
        *extra,
    ]


def test_sync_writes_then_check_passes(tmp_path: Path) -> None:
    runs, readme, bullets = _setup(tmp_path)
    assert main(_args(runs, readme, bullets)) == 0
    assert "75.0%" in readme.read_text("utf-8")
    assert "75.0%" in bullets.read_text("utf-8")
    assert main(_args(runs, readme, bullets, "--check")) == 0


def test_check_fails_when_a_file_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs, readme, bullets = _setup(tmp_path)
    assert main(_args(runs, readme, bullets)) == 0
    append_run(runs, run("N1", "b2", 0.8, ci=(0.75, 0.85)))
    assert main(_args(runs, readme, bullets, "--check")) == 1
    assert "stale" in capsys.readouterr().err
