"""One filing's HTML to its sections and chunks. Pure: no I/O."""

import hashlib
from collections.abc import Sequence

from sec_agent.filings.annual_report import find_annual_report_documents
from sec_agent.filings.chunking import chunk_spans
from sec_agent.filings.html_text import html_blocks
from sec_agent.filings.incorporation import merge_sections
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import Chunk, ExhibitDocument, FilingRef, IndexedFiling, Section
from sec_agent.filings.sections import find_sections
from sec_agent.filings.tokens import count_tokens


def index_filing(
    html: bytes,
    filing: FilingRef,
    config: ChunkConfig,
    exhibits: Sequence[ExhibitDocument] = (),
) -> IndexedFiling:
    """Index the primary document; `exhibits` are the filing's Exhibit 13 documents, which
    fill the 10-K items it incorporates by reference (see `incorporation`)."""
    version = index_version(config)
    sections = tuple(_sections(html, filing, exhibits))
    chunks = tuple(
        chunk for section in sections for chunk in _chunks(section, filing, version, config)
    )
    return IndexedFiling(index_version=version, filing=filing, sections=sections, chunks=chunks)


def _sections(html: bytes, filing: FilingRef, exhibits: Sequence[ExhibitDocument]) -> list[Section]:
    primary = find_sections(html_blocks(html), filing.form)
    if not exhibits:
        return primary
    # Split exhibits (EX-13.1, EX-13.2) are one report cut into files: read them together.
    report = [(exhibit.url, html_blocks(exhibit.html)) for exhibit in exhibits]
    return merge_sections(primary, find_annual_report_documents(report), filing.form)


def _spans(section: Section, max_tokens: int) -> list[tuple[int, int, str | None]]:
    """Chunk spans with the document each one's text came from. A section split over
    several exhibits is chunked one document at a time, so no chunk crosses into the next
    document and each cites the file its own text is in."""
    if not section.documents:
        return [(s, e, None) for s, e in chunk_spans(section.text, max_tokens)]
    ends = [d.start for d in section.documents[1:]] + [len(section.text)]
    return [
        (doc.start + s, doc.start + e, doc.url)
        for doc, end in zip(section.documents, ends, strict=True)
        for s, e in chunk_spans(section.text[doc.start : end], max_tokens)
    ]


def _chunks(section: Section, filing: FilingRef, version: str, config: ChunkConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    for ordinal, (start, end, source_url) in enumerate(_spans(section, config.max_tokens)):
        text = section.text[start:end]
        chunks.append(
            Chunk(
                index_version=version,
                accession=filing.accession,
                cik=filing.cik,
                form=filing.form,
                filing_date=filing.filing_date,
                report_date=filing.report_date,
                section=section.key,
                ordinal=ordinal,
                char_start=start,
                char_end=end,
                token_count=count_tokens(text),
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                source_url=source_url,
            )
        )
    return chunks
