"""One filing's HTML to its sections and chunks. Pure: no I/O."""

import hashlib
from collections.abc import Sequence

from sec_agent.filings.annual_report import find_annual_report_sections
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
    # Split exhibits (EX-13.1, EX-13.2) may each hold part of the report: the longest text
    # of a part wins, as for a heading repeated inside one document.
    best: dict[str, Section] = {}
    for exhibit in exhibits:
        for section in find_annual_report_sections(html_blocks(exhibit.html), exhibit.url):
            if section.key not in best or len(section.text) > len(best[section.key].text):
                best[section.key] = section
    return merge_sections(primary, list(best.values()), filing.form)


def _chunks(section: Section, filing: FilingRef, version: str, config: ChunkConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    for ordinal, (start, end) in enumerate(chunk_spans(section.text, config.max_tokens)):
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
            )
        )
    return chunks
