"""One filing's HTML to its sections and chunks. Pure: no I/O."""

import hashlib

from sec_agent.filings.chunking import chunk_spans
from sec_agent.filings.html_text import html_blocks
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import Chunk, FilingRef, IndexedFiling, Section
from sec_agent.filings.sections import find_sections
from sec_agent.filings.tokens import count_tokens


def index_filing(html: bytes, filing: FilingRef, config: ChunkConfig) -> IndexedFiling:
    version = index_version(config)
    sections = tuple(find_sections(html_blocks(html), filing.form))
    chunks = tuple(
        chunk for section in sections for chunk in _chunks(section, filing, version, config)
    )
    return IndexedFiling(index_version=version, filing=filing, sections=sections, chunks=chunks)


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
