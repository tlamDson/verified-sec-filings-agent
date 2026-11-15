"""Embedding spaces: one name per (chunk build, embedding model and settings)."""

import pytest
from pydantic import ValidationError
from retrieval_fakes import HASH_SPEC

from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.space import hnsw_index_name, make_space, space_name

VERSION = "chunks-p1-t400-0123abcd"


def test_name_starts_with_the_chunk_version_and_is_stable() -> None:
    name = space_name(VERSION, HASH_SPEC)
    assert name.startswith(f"{VERSION}.e-")
    assert "d16" in name
    assert name == space_name(VERSION, HASH_SPEC.model_copy())


@pytest.mark.parametrize(
    "change",
    [
        {"model": "test/other"},
        {"dimensions": 8},
        {"normalized": False},
        {"query_prefix": ""},
        {"passage_prefix": ""},
        {"max_input_tokens": 512},
    ],
)
def test_any_setting_that_changes_vectors_changes_the_name(change: dict[str, object]) -> None:
    other = HASH_SPEC.model_copy(update=change)
    assert space_name(VERSION, other) != space_name(VERSION, HASH_SPEC)


def test_another_chunk_version_is_another_space() -> None:
    assert space_name("chunks-p2-t400-ffffffff", HASH_SPEC) != space_name(VERSION, HASH_SPEC)


def test_make_space_carries_version_and_spec() -> None:
    space = make_space(VERSION, HASH_SPEC)
    assert (space.name, space.index_version, space.spec) == (
        space_name(VERSION, HASH_SPEC),
        VERSION,
        HASH_SPEC,
    )


def test_hnsw_index_name_fits_a_postgres_identifier() -> None:
    long_version = "chunks-p1-t400-" + "a" * 60
    name = hnsw_index_name(space_name(long_version, HASH_SPEC))
    assert len(name) <= 63
    assert name.isidentifier()
    assert name != hnsw_index_name(space_name(VERSION, HASH_SPEC))


@pytest.mark.parametrize("dimensions", [0, 2001])
def test_dimensions_must_fit_an_hnsw_index(dimensions: int) -> None:
    with pytest.raises(ValidationError):
        EmbedderSpec(model="m", dimensions=dimensions, normalized=True)
