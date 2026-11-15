"""What `sec-agent mcp` serves from: one facts version, and the serving (or a named) snapshot.

Facts are the recorded Apple and NVIDIA companyfacts; filing text is simulated.
"""

from typing import Any

import psycopg
import pytest
from retrieval_corpus import CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder
from tools_data import APPLE_CIK, FACTS_VERSION

from sec_agent.cli import build_parser, main
from sec_agent.mcp_server.contexts import ServeConfigError, open_contexts
from sec_agent.mcp_server.dispatch import call_tool
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.snapshot import activate, create_snapshot
from sec_agent.retrieval.space import make_space
from sec_agent.xbrl.models import Fact, NormalizationReport
from sec_agent.xbrl.normalize import Normalized
from sec_agent.xbrl.store import PostgresFactStore


@pytest.fixture
def facts_db(tools_db: str, recorded_facts: dict[int, list[Fact]]) -> str:
    with PostgresFactStore.connect(tools_db) as store:
        store.write(
            index_version=FACTS_VERSION,
            cik=APPLE_CIK,
            entity_name="Apple Inc.",
            normalized=Normalized(facts=recorded_facts[APPLE_CIK], report=NormalizationReport()),
        )
    return tools_db


def _no_embedder(spec: EmbedderSpec) -> HashEmbedder | None:
    return None


def test_facts_are_served_from_postgres_without_a_text_index(facts_db: str) -> None:
    with open_contexts(facts_db, facts_version=FACTS_VERSION, embedder=_no_embedder) as ctx:
        assert ctx.text is None
        assert ctx.facts.index_version == FACTS_VERSION
        outcome = call_tool(
            ctx, "get_fact", {"company": "AAPL", "concept": "revenue", "fiscal_year": 2024}
        )
    assert not outcome.is_error
    assert outcome.payload["fact"]["value"] == "391035000000"


def test_a_facts_version_with_no_facts_is_refused(facts_db: str) -> None:
    with (
        pytest.raises(ServeConfigError, match="x-missing"),
        open_contexts(facts_db, facts_version="x-missing", embedder=_no_embedder),
    ):
        pass


def test_a_named_snapshot_that_does_not_exist_is_refused(facts_db: str) -> None:
    with (
        pytest.raises(ServeConfigError, match="nope"),
        open_contexts(
            facts_db, facts_version=FACTS_VERSION, snapshot="nope", embedder=_no_embedder
        ),
    ):
        pass


def test_the_serving_snapshot_pins_the_text_tools(
    facts_db: str, tools_conn: psycopg.Connection[Any]
) -> None:
    store_corpus(facts_db, CONFIG)
    build_index(tools_conn, VERSION, HashEmbedder())
    space = make_space(VERSION, HASH_SPEC)
    create_snapshot(tools_conn, "sim-snap", space)
    activate(tools_conn, "sim-snap")
    asked: list[EmbedderSpec] = []

    def embedder(spec: EmbedderSpec) -> HashEmbedder:
        asked.append(spec)
        return HashEmbedder()

    with open_contexts(facts_db, facts_version=FACTS_VERSION, embedder=embedder) as ctx:
        assert ctx.text is not None
        assert ctx.text.space == space
        assert ctx.text.facts_version == FACTS_VERSION
        assert isinstance(ctx.text.embedder, HashEmbedder)
        outcome = call_tool(ctx, "search_filings", {"query": "simulated parts", "k": 2})
    assert asked == [HASH_SPEC]
    assert not outcome.is_error
    assert outcome.payload["index_version"] == VERSION


def test_cli_has_an_mcp_command() -> None:
    args = build_parser().parse_args(["mcp", "--facts-version", "v1", "--lexical"])
    assert args.facts_version == "v1"
    assert args.lexical is True
    assert args.snapshot is None
    assert callable(args.run)


def test_cli_mcp_needs_a_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["mcp", "--facts-version", "v1"]) == 2
    out = capsys.readouterr()
    assert out.out == ""  # stdout belongs to the MCP protocol
    assert "DATABASE_URL" in out.err


def test_cli_mcp_reports_a_bad_facts_version_on_stderr(
    facts_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["mcp", "--database-url", facts_db, "--facts-version", "x-missing", "--lexical"])
    assert code == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert "x-missing" in out.err
