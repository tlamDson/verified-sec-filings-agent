"""The small indexed corpus the retrieval tests share. Simulated filings only.

Three filings: the simulated 10-K and 10-Q of one company, and the same 10-K filed under a
second simulated CIK, so identical passages tie and the tie-break is exercised.
"""

import datetime as dt
from pathlib import Path

from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import FilingRef
from sec_agent.filings.pipeline import index_filing
from sec_agent.filings.store import PostgresChunkStore

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "filings"
CONFIG = ChunkConfig(max_tokens=30)
OTHER_CONFIG = ChunkConfig(max_tokens=60)
VERSION = index_version(CONFIG)
OTHER_VERSION = index_version(OTHER_CONFIG)

CIK_A = "9999999999"
CIK_B = "9999999998"

FILING_10K = FilingRef(
    cik=CIK_A,
    accession="9999999999-25-000008",
    form="10-K",
    filing_date=dt.date(2025, 2, 20),
    report_date=dt.date(2024, 12, 31),
    primary_document="simw-20241231.htm",
)
FILING_10Q = FilingRef(
    cik=CIK_A,
    accession="9999999999-24-000005",
    form="10-Q",
    filing_date=dt.date(2024, 8, 1),
    report_date=dt.date(2024, 6, 30),
    primary_document="simw-20240630.htm",
)
FILING_10K_B = FilingRef(
    cik=CIK_B,
    accession="9999999998-24-000003",
    form="10-K",
    filing_date=dt.date(2024, 2, 15),
    report_date=dt.date(2023, 12, 31),
    primary_document="simb-20231231.htm",
)
CORPUS = ((FILING_10K, "sim-10k.htm"), (FILING_10Q, "sim-10q.htm"), (FILING_10K_B, "sim-10k.htm"))


def store_corpus(conninfo: str, config: ChunkConfig) -> int:
    """Index and store the three filings under `config`; return the number of chunks."""
    total = 0
    with PostgresChunkStore.connect(conninfo) as store:
        for filing, name in CORPUS:
            indexed = index_filing((FIXTURES / name).read_bytes(), filing, config)
            store.replace(indexed)
            total += len(indexed.chunks)
    return total
