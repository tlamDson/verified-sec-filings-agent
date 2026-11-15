"""`sec-agent index init|build|snapshot|verify|activate|search`."""

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from retrieval_corpus import FILING_10Q, VERSION
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.cli import main
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.snapshot import read_manifest
from sec_agent.retrieval.space import make_space

Conn = psycopg.Connection[Any]


@pytest.fixture
def built(conn: Conn, corpus_db: str, monkeypatch: pytest.MonkeyPatch) -> str:
    build_index(conn, VERSION, HashEmbedder())
    monkeypatch.setenv("DATABASE_URL", corpus_db)
    return make_space(VERSION, HASH_SPEC).name


def test_index_init_creates_the_tables(
    pg_uri: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_uri)
    assert main(["index", "init"]) == 0
    assert "retrieval schema ready" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [["index", "build"], ["index", "snapshot", "x"], ["index", "search", "q"]],
)
def test_commands_need_a_database_url(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(argv) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_snapshot_verify_activate_then_search(
    built: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "eval.json"
    assert main(["index", "snapshot", "eval", "--space", built, "--manifest", str(manifest)]) == 0
    out = capsys.readouterr().out
    snapshot = read_manifest(manifest)
    assert snapshot.content_sha256 in out
    assert main(["index", "verify", "eval"]) == 0
    assert "ok" in capsys.readouterr().out
    assert main(["index", "activate", "eval"]) == 0
    assert "serving -> eval" in capsys.readouterr().out

    assert main(["index", "search", "gross margin", "--mode", "lexical", "-k", "2", "--json"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["rank"] == 1
    assert first["index_version"] == VERSION
    assert first["source_url"].startswith("https://www.sec.gov/Archives/")

    assert main(["index", "search", "gross margin", "--mode", "lexical", "--cik", "1"]) == 0
    assert "no passages" in capsys.readouterr().out


def test_verify_fails_after_the_content_changed(
    built: str, conn: Conn, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["index", "snapshot", "eval", "--space", built]) == 0
    conn.execute(b"DELETE FROM indexed_filings WHERE accession = %s", (FILING_10Q.accession,))
    assert main(["index", "verify", "eval"]) == 1
    assert "changed" in capsys.readouterr().err


def test_search_without_a_serving_snapshot_says_so(
    built: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["index", "search", "gross margin", "--mode", "lexical"]) == 2
    assert "index activate" in capsys.readouterr().err


def test_snapshot_of_an_unknown_space_fails(built: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["index", "snapshot", "eval", "--space", "nope"]) == 1
    assert "nope" in capsys.readouterr().err
