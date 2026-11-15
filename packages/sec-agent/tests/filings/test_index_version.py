"""`index_version`: one deterministic name per parser and chunking configuration."""

import re

import pytest
from pydantic import ValidationError

from sec_agent.filings.index_version import PARSER_VERSION, ChunkConfig, index_version


def test_default_config_targets_400_tokens() -> None:
    assert ChunkConfig().max_tokens == 400


def test_same_config_gives_the_same_version() -> None:
    assert index_version(ChunkConfig()) == index_version(ChunkConfig(max_tokens=400))


def test_version_names_parser_and_size_and_ends_in_a_digest() -> None:
    version = index_version(ChunkConfig(max_tokens=300))
    assert re.fullmatch(rf"chunks-p{PARSER_VERSION}-t300-[0-9a-f]{{8}}", version)


def test_any_config_change_gives_a_new_version() -> None:
    assert index_version(ChunkConfig(max_tokens=300)) != index_version(ChunkConfig())


@pytest.mark.parametrize("max_tokens", [0, 10, 5000])
def test_config_rejects_unusable_sizes(max_tokens: int) -> None:
    with pytest.raises(ValidationError):
        ChunkConfig(max_tokens=max_tokens)
