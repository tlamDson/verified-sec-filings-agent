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
from sec_agent.filings.models import ExhibitDocument, FilingRef, IndexedFiling, Section
from sec_agent.filings.pipeline import index_filing

# Digest of every chunk the default configuration makes on each pinned ingest path. When
# parser or chunker output changes on purpose, bump PARSER_VERSION (so a new index_version
# is built beside the old one instead of silently mixing into it) and record the new
# digests here.
PINNED_VERSION = "chunks-p3-t400-"
PINNED = {
    "10-K": "d62d7198f3fad75cadb5a83bf35e5c7f61bcbdb3d0d4685d926de80ba6d88648",
    "10-Q": "6940c401504be55ffa0c3160101a9d4874b78b83dca502ddcce381dd734ffb3a",
    "10-K + EX-13": "a7e4fea5fe628bfd6e122dfaa11ab5e254c0f8ad5bd3d3144ed0be9f4a746011",
    "10-K + EX-13.1, EX-13.2": "6f7f2cf356a6ba92e818c416a1cc4fec20e67a928b6fbe971037c62a846ef5f3",
}

Read = Callable[[str], bytes]


def _chunk_digest(indexed: IndexedFiling) -> str:
    rows = [c.model_dump(mode="json") for c in indexed.chunks]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def _pinned_builds(
    read: Read, filing_10k: FilingRef, filing_10q: FilingRef
) -> dict[str, IndexedFiling]:
    """One build per ingest path: a 10-K, a 10-Q, and a 10-K that incorporates items by
    reference to an Exhibit 13 filed as one document or split over two."""
    config = ChunkConfig()
    folder = filing_10k.document_url.rsplit("/", 1)[0]
    exhibit = ExhibitDocument(url=f"{folder}/simb-ex13.htm", html=read("sim-ex13.htm"))
    split = (
        ExhibitDocument(
            url=f"{folder}/simb-ex13.htm",
            html=b"<div>Financial Review</div><p>Simulated net income rose on simulated fees.</p>",
        ),
        ExhibitDocument(
            url=f"{folder}/simb-ex13_2.htm",
            html=b"<p>Simulated deposit costs rose faster than simulated loan yields.</p>"
            b"<div>Controls and Procedures</div><p>Simulated controls.</p>",
        ),
    )
    ibr = read("sim-10k-ibr.htm")
    return {
        "10-K": index_filing(read("sim-10k.htm"), filing_10k, config),
        "10-Q": index_filing(read("sim-10q.htm"), filing_10q, config),
        "10-K + EX-13": index_filing(ibr, filing_10k, config, (exhibit,)),
        "10-K + EX-13.1, EX-13.2": index_filing(ibr, filing_10k, config, split),
    }


def _digests(read: Read, filing_10k: FilingRef, filing_10q: FilingRef) -> dict[str, str]:
    builds = _pinned_builds(read, filing_10k, filing_10q)
    return {path: _chunk_digest(b) for path, b in builds.items()}


def test_output_is_pinned_to_the_parser_version(
    read_fixture: Read, filing_10k: FilingRef, filing_10q: FilingRef
) -> None:
    builds = _pinned_builds(read_fixture, filing_10k, filing_10q)
    assert all(b.index_version.startswith(PINNED_VERSION) for b in builds.values())
    assert _digests(read_fixture, filing_10k, filing_10q) == PINNED, (
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
    filing_10q: FilingRef,
    change: Callable[[pytest.MonkeyPatch], None],
) -> None:
    before = _digests(read_fixture, filing_10k, filing_10q)
    change(monkeypatch)
    after = _digests(read_fixture, filing_10k, filing_10q)
    assert after != before, (
        "Exhibit 13 chunk output changed but the pin did not: PARSER_VERSION stays, so the "
        "build reuses the old index_version and serves the stale index as current"
    )
