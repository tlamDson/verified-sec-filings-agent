"""What the tools read from, pinned for one request: a facts snapshot, or a text index."""

from dataclasses import dataclass
from typing import Any

import psycopg

from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.models import EmbeddingSpace
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.fact_query import FactQuery
from sec_agent.tools.risk_sections import RiskSectionSource


@dataclass(frozen=True)
class FactsContext:
    """For `get_fact`, `compute_ratio`, `compare_peers`: one facts `index_version`."""

    companies: CompanyDirectory
    facts: FactQuery
    index_version: str


@dataclass(frozen=True)
class TextContext:
    """For `search_filings` and `diff_risk_factors`: one embedding space (so one chunk
    `index_version` and one model). `facts_version` labels 10-Ks with fiscal years (E1).
    Without an embedder, search runs on BM25 alone and says so."""

    companies: CompanyDirectory
    conn: psycopg.Connection[Any]
    space: EmbeddingSpace
    sections: RiskSectionSource
    facts_version: str
    embedder: Embedder | None = None
