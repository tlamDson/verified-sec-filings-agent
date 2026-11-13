"""`sec-agent chaos ...`: fake model, integrity check, worker kill, load rows."""

import json
import shutil
from pathlib import Path

import psycopg
import pytest

from sec_agent.cli import build_parser, main
from sec_agent.runs import read_runs

SUMMARY = Path(__file__).parent.parent / "fixtures" / "k6" / "summary.sim.json"


def test_chaos_commands_are_wired() -> None:
    parser = build_parser()
    for argv in (
        ["chaos", "fake-llm", "--port", "9"],
        ["chaos", "integrity", "--index-version", "v1"],
        ["chaos", "kill-worker", "--index-version", "v1"],
        ["chaos", "load-rows", "s.json", "--system", "x"],
    ):
        assert callable(parser.parse_args(argv).run)


def test_load_rows_appends_valid_rows(tmp_path: Path) -> None:
    runs = tmp_path / "runs.csv"
    shutil.copy(SUMMARY, tmp_path / "summary.json")
    code = main(
        [
            "chaos",
            "load-rows",
            str(tmp_path / "summary.json"),
            "--system",
            "api-x3+fake-llm",
            "--config",
            "200 VU",
            "--git-sha",
            "abc1234",
            "--record",
            str(runs),
        ]
    )
    assert code == 0
    rows = read_runs(runs)
    assert len(rows) == 6  # the fixture has interrupted conversations
    assert {row.cohort for row in rows} == {"simulated"}


def test_load_rows_refuses_a_summary_without_the_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"metrics": {}}', "utf-8")
    argv = ["chaos", "load-rows", str(bad), "--system", "x", "--git-sha", "abc1234"]
    assert main([*argv, "--record", str(tmp_path / "runs.csv")]) == 2
    assert "turn_failed" in capsys.readouterr().err
    assert not (tmp_path / "runs.csv").exists()


def test_integrity_prints_json_and_fails_when_nothing_was_ingested(
    facts_db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", facts_db_url)
    assert main(["chaos", "integrity", "--index-version", "v9"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["index_version"] == "v9"
    assert report["clean"] is False


def test_integrity_passes_on_a_whole_ingest(
    facts_db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with psycopg.connect(facts_db_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO jobs (kind, key, status, attempts, finished_at) "
            "VALUES ('xbrl.companyfacts', 'v1:0000000001', 'done', 1, now())"
        )
        conn.execute(
            "INSERT INTO xbrl_ingests (index_version, cik, entity_name, facts_written, report) "
            "VALUES ('v1', 1, 'Test Co', 0, '{}')"
        )
    monkeypatch.setenv("DATABASE_URL", facts_db_url)
    assert main(["chaos", "integrity", "--index-version", "v1"]) == 0
    assert json.loads(capsys.readouterr().out)["clean"] is True


def test_kill_worker_needs_a_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["chaos", "kill-worker", "--index-version", "v1"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err
