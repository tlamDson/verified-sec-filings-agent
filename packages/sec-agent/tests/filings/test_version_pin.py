"""The guard that ties `index_version` to chunk output: change the output, bump the version.

`index_version` is derived from PARSER_VERSION and the chunk configuration, not from code,
so a chunking change keeps the old name, and the build reuses the old index (same job keys,
same rows) unless PARSER_VERSION is bumped. The pin below fails on any output change of an
ingest path it builds; a path it does not build can change under the old name.
"""

import hashlib
import json
from collections.abc import Callable

import pytest

from sec_agent.filings import incorporation, pipeline
from sec_agent.filings.chunking import chunk_spans
from sec_agent.filings.index_version import ChunkConfig
from sec_agent.filings.models import FilingRef, IndexedFiling, Section
from sec_agent.filings.pipeline import index_filing

# Digest of every chunk the default configuration makes on each pinned ingest path. When
# parser or chunker output changes on purpose, bump PARSER_VERSION (so a new index_version
# is built beside the old one instead of silently mixing into it) and record the new
# digests here.
PINNED_VERSION = "chunks-p3-t400-"
PINNED = {
    "10-K": "d62d7198f3fad75cadb5a83bf35e5c7f61bcbdb3d0d4685d926de80ba6d88648",
}

Read = Callable[[str], bytes]


def _chunk_digest(indexed: IndexedFiling) -> str:
    rows = [c.model_dump(mode="json") for c in indexed.chunks]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def _pinned_builds(read: Read, filing_10k: FilingRef) -> dict[str, IndexedFiling]:
    config = ChunkConfig()
    return {"10-K": index_filing(read("sim-10k.htm"), filing_10k, config)}


def _digests(read: Read, filing_10k: FilingRef) -> dict[str, str]:
    return {path: _chunk_digest(b) for path, b in _pinned_builds(read, filing_10k).items()}


def test_output_is_pinned_to_the_parser_version(read_fixture: Read, filing_10k: FilingRef) -> None:
    builds = _pinned_builds(read_fixture, filing_10k)
    assert all(b.index_version.startswith(PINNED_VERSION) for b in builds.values())
    assert _digests(read_fixture, filing_10k) == PINNED, (
        "parser output changed: bump PARSER_VERSION"
    )


def _chunk_split_part_as_one_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """The chunking before s-06c's fix: a part split over EX-13.1 and EX-13.2 is chunked as
    one text, so a chunk can cross from one exhibit into the next."""
    original = pipeline._spans  # pyright: ignore[reportPrivateUsage]

    def spans(section: Section, max_tokens: int) -> list[tuple[int, int, str | None]]:
        if not section.documents:
            return original(section, max_tokens)
        url = section.documents[0].url
        return [(s, e, url) for s, e in chunk_spans(section.text, max_tokens)]

    monkeypatch.setattr(pipeline, "_spans", spans)


def _read_shorter_pointers_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tuning of which 10-K items count as pointers to Exhibit 13."""
    monkeypatch.setattr(incorporation, "STUB_MAX_TOKENS", 40)


@pytest.mark.parametrize(
    "change",
    [_chunk_split_part_as_one_text, _read_shorter_pointers_only],
    ids=["split-exhibit-chunking", "pointer-threshold"],
)
def test_a_change_to_exhibit_13_ingest_fails_the_pin(
    monkeypatch: pytest.MonkeyPatch,
    read_fixture: Read,
    filing_10k: FilingRef,
    change: Callable[[pytest.MonkeyPatch], None],
) -> None:
    before = _digests(read_fixture, filing_10k)
    change(monkeypatch)
    after = _digests(read_fixture, filing_10k)
    assert after != before, (
        "Exhibit 13 chunk output changed but the pin did not: PARSER_VERSION stays, so the "
        "build reuses the old index_version and serves the stale index as current"
    )
