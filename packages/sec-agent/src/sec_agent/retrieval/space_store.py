"""Embedding spaces in Postgres: register once, then every reader checks what it pins."""

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from sec_agent.retrieval.errors import EmbeddingMismatchError, IndexNotBuiltError
from sec_agent.retrieval.models import EmbedderSpec, EmbeddingSpace

_INSERT = b"""
INSERT INTO embedding_spaces (name, index_version, model, dimensions, spec)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (name) DO NOTHING
"""
_SELECT = b"SELECT name, index_version, spec FROM embedding_spaces WHERE name = %s"


def load_space(conn: psycopg.Connection[Any], name: str) -> EmbeddingSpace | None:
    row = conn.execute(_SELECT, (name,)).fetchone()
    if row is None:
        return None
    return EmbeddingSpace(
        name=str(row[0]), index_version=str(row[1]), spec=EmbedderSpec.model_validate(row[2])
    )


def register_space(conn: psycopg.Connection[Any], space: EmbeddingSpace) -> None:
    """Insert the space, or check that the stored one is the same."""
    spec = space.spec
    conn.execute(
        _INSERT,
        (space.name, space.index_version, spec.model, spec.dimensions, Jsonb(spec.model_dump())),
    )
    require_space(conn, space)


def require_space(conn: psycopg.Connection[Any], space: EmbeddingSpace) -> None:
    """Raise unless the database holds exactly this space."""
    stored = load_space(conn, space.name)
    if stored is None:
        raise IndexNotBuiltError(f"embedding space {space.name} was never built")
    if stored != space:
        raise EmbeddingMismatchError(
            f"embedding space {space.name} holds {stored.spec.model} for {stored.index_version};"
            f" asked for {space.spec.model} for {space.index_version}"
        )
