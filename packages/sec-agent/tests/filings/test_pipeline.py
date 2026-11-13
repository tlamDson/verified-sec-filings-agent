"""`index_filing`: one filing's HTML to sections and chunks that carry their metadata."""

import hashlib
import json
from collections.abc import Callable

from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import FilingRef, IndexedFiling
from sec_agent.filings.pipeline import index_filing
from sec_agent.filings.tokens import count_tokens

SMALL = ChunkConfig(max_tokens=30)

# Digest of every chunk the default configuration makes from sim-10k.htm. When parser or
# chunker output changes on purpose, bump PARSER_VERSION (so a new index_version is built
# beside the old one instead of silently mixing into it) and record the new digest here.
PINNED_VERSION = "chunks-p1-t400-"
PINNED_DIGEST = "a4592aec953005d8beb084232368713728132773d3a01898310f3093cca55891"


def _digest(indexed: IndexedFiling) -> str:
    rows = [c.model_dump(mode="json") for c in indexed.chunks]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def test_chunks_carry_filing_section_and_version_metadata(
    read_fixture: Callable[[str], bytes], filing_10k: FilingRef
) -> None:
    indexed = index_filing(read_fixture("sim-10k.htm"), filing_10k, SMALL)
    assert indexed.filing == filing_10k
    assert indexed.index_version == index_version(SMALL)
    assert [s.key for s in indexed.sections] == ["business", "risk_factors", "mdna", "market_risk"]
    assert indexed.chunks
    for chunk in indexed.chunks:
        assert chunk.index_version == index_version(SMALL)
        assert chunk.accession == filing_10k.accession
        assert chunk.cik == filing_10k.cik
        assert chunk.form == "10-K"
        assert chunk.filing_date == filing_10k.filing_date
        assert chunk.report_date == filing_10k.report_date
        assert chunk.token_count == count_tokens(chunk.text) <= SMALL.max_tokens
        assert chunk.text_sha256 == hashlib.sha256(chunk.text.encode()).hexdigest()


def test_chunk_offsets_point_into_their_section_text(
    read_fixture: Callable[[str], bytes], filing_10k: FilingRef
) -> None:
    indexed = index_filing(read_fixture("sim-10k.htm"), filing_10k, SMALL)
    sections = {s.key: s for s in indexed.sections}
    for key, section in sections.items():
        chunks = [c for c in indexed.chunks if c.section == key]
        assert [c.ordinal for c in chunks] == list(range(len(chunks)))
        for chunk in chunks:
            assert section.text[chunk.char_start : chunk.char_end] == chunk.text
    assert len([c for c in indexed.chunks if c.section == "business"]) > 1


def test_10q_chunks(read_fixture: Callable[[str], bytes], filing_10q: FilingRef) -> None:
    indexed = index_filing(read_fixture("sim-10q.htm"), filing_10q, ChunkConfig())
    assert {c.section for c in indexed.chunks} == {"mdna", "risk_factors"}
    assert all(c.form == "10-Q" for c in indexed.chunks)


def test_filing_without_text_items_indexes_no_chunks(
    read_fixture: Callable[[str], bytes], filing_10k: FilingRef
) -> None:
    amendment = filing_10k.model_copy(update={"form": "10-K/A"})
    indexed = index_filing(read_fixture("sim-10ka-part3.htm"), amendment, ChunkConfig())
    assert indexed.sections == ()
    assert indexed.chunks == ()


def test_output_is_pinned_to_the_parser_version(
    read_fixture: Callable[[str], bytes], filing_10k: FilingRef
) -> None:
    indexed = index_filing(read_fixture("sim-10k.htm"), filing_10k, ChunkConfig())
    assert indexed.index_version.startswith(PINNED_VERSION)
    assert _digest(indexed) == PINNED_DIGEST, "parser output changed: bump PARSER_VERSION"
