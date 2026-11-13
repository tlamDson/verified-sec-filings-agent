"""Names of embedding spaces and of their HNSW indexes.

A space name is derived from the chunk build and every embedding setting that changes the
vectors, so a new model, or new prefixes, give a new space beside the old one (blue/green).
"""

import hashlib
import re

from sec_agent.retrieval.models import EmbedderSpec, EmbeddingSpace

_SLUG = re.compile(r"[^a-z0-9]+")


def space_name(index_version: str, spec: EmbedderSpec) -> str:
    """`<index_version>.e-<model slug>-d<dims>-<8 hex digest of the whole spec>`."""
    digest = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:8]
    slug = _SLUG.sub("-", spec.model.lower()).strip("-")
    return f"{index_version}.e-{slug}-d{spec.dimensions}-{digest}"


def make_space(index_version: str, spec: EmbedderSpec) -> EmbeddingSpace:
    name = space_name(index_version, spec)
    return EmbeddingSpace(name=name, index_version=index_version, spec=spec)


def hnsw_index_name(space: str) -> str:
    """A Postgres identifier (at most 63 bytes) unique to the space."""
    return f"chunk_embeddings_hnsw_{hashlib.sha256(space.encode()).hexdigest()[:16]}"
