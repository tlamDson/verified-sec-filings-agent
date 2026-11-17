"""The tool contexts keep working after the server drops their connections (idle timeout,
restart): the facts lookup and the text search each open a fresh connection."""

from typing import Any

import psycopg
import pytest
from pg_kill import client_backends, terminate
from retrieval_corpus import CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder
from tools_data import APPLE_CIK, FACTS_VERSION

from sec_agent.mcp_server.contexts import open_contexts
from sec_agent.mcp_server.dispatch import call_tool
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.snapshot import activate, create_snapshot
from sec_agent.retrieval.space import make_space
from sec_agent.xbrl.models import Fact, NormalizationReport
from sec_agent.xbrl.normalize import Normalized
from sec_agent.xbrl.store import PostgresFactStore

REVENUE = {"company": "AAPL", "concept": "revenue", "fiscal_year": 2024}


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


def _embedder(spec: EmbedderSpec) -> HashEmbedder:
    return HashEmbedder()


def test_facts_and_search_answer_after_the_server_dropped_the_connections(
    facts_db: str, tools_conn: psycopg.Connection[Any]
) -> None:
    store_corpus(facts_db, CONFIG)
    build_index(tools_conn, VERSION, HashEmbedder())
    create_snapshot(tools_conn, "sim-snap", make_space(VERSION, HASH_SPEC))
    activate(tools_conn, "sim-snap")
    before = client_backends(facts_db)
    with open_contexts(facts_db, facts_version=FACTS_VERSION, embedder=_embedder) as ctx:
        assert not call_tool(ctx, "get_fact", REVENUE).is_error
        terminate(facts_db, client_backends(facts_db) - before)
        fact = call_tool(ctx, "get_fact", REVENUE)
        search = call_tool(ctx, "search_filings", {"query": "simulated parts", "k": 2})
    assert not fact.is_error
    assert fact.payload["fact"]["value"] == "391035000000"
    assert not search.is_error
    assert search.payload["index_version"] == VERSION
