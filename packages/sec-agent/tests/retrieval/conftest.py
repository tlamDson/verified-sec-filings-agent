"""Fixtures for hybrid retrieval: the corpus of `retrieval_corpus`, stored and ready."""

from collections.abc import Iterator

import psycopg
import pytest
from retrieval_corpus import CONFIG, OTHER_CONFIG, store_corpus
from retrieval_fakes import HashEmbedder

from sec_agent.retrieval.schema import apply_schema


@pytest.fixture
def retrieval_db(db_url: str) -> str:
    """The chunk and retrieval schemas applied, every table empty."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute(
            "TRUNCATE indexed_filings, embedding_spaces, lexical_stats, lexical_df CASCADE"
        )
    return db_url


@pytest.fixture
def corpus_db(retrieval_db: str) -> str:
    """`retrieval_db` with the corpus stored under VERSION and under OTHER_VERSION."""
    store_corpus(retrieval_db, CONFIG)
    store_corpus(retrieval_db, OTHER_CONFIG)
    return retrieval_db


@pytest.fixture
def conn(corpus_db: str) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with psycopg.connect(corpus_db, autocommit=True) as connection:
        yield connection


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder()
