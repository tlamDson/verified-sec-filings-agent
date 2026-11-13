"""FinanceBench's open-source sample (Patronus AI) as G-public questions.

Two files from `data/` of https://github.com/patronus-ai/financebench: the questions
(`financebench_open_source.jsonl`) and the document records they cite
(`financebench_document_information.jsonl`), joined on `doc_name`. Neither is committed
here: they are read from a local download, and only when the manifest says the licence and
the answers were checked and both files match their pins.

Each question gets the company's ticker and split when the company is in the universe.
A question is `in_scope` when its company is in the company split and its document is a
10-K or 10-Q; others (8-K, earnings releases, companies outside the 50) are kept but
marked, so they can be counted apart (E7).
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.public.manifest import GPublicManifest, check_manifest
from sec_agent.golden.split import CompanySplit
from sec_agent.runs import Split

QUESTIONS_FILE = "financebench_open_source.jsonl"
DOCUMENTS_FILE = "financebench_document_information.jsonl"
FILING_DOC_TYPES = frozenset({"10k", "10q"})

# FinanceBench company names -> universe tickers, for the names in the open sample that are
# S&P 100 companies. Companies outside the universe (Amcor, Best Buy, MGM Resorts, ...) are
# deliberately absent.
FINANCEBENCH_TICKERS: dict[str, str] = {
    "3M": "MMM",
    "AMD": "AMD",
    "Adobe": "ADBE",
    "Amazon": "AMZN",
    "American Express": "AXP",
    "Boeing": "BA",
    "CVS Health": "CVS",
    "Coca-Cola": "KO",
    "Costco": "COST",
    "JPMorgan": "JPM",
    "Johnson & Johnson": "JNJ",
    "Lockheed Martin": "LMT",
    "Microsoft": "MSFT",
    "Netflix": "NFLX",
    "PepsiCo": "PEP",
    "Pfizer": "PFE",
    "Verizon": "VZ",
    "Walmart": "WMT",
}


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    evidence_text: str
    doc_name: str
    evidence_page_num: int


class FinanceBenchRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    financebench_id: str
    company: str
    doc_name: str
    question_type: str
    question_reasoning: str | None = None
    question: str
    answer: str
    justification: str | None = None
    evidence: tuple[Evidence, ...] = ()


class FinanceBenchDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    doc_name: str
    company: str
    gics_sector: str
    doc_type: str
    doc_period: int
    doc_link: str


class PublicQuestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: str = "financebench"
    company: str
    ticker: str | None
    cik: int | None
    split: Split
    in_scope: bool
    doc_name: str
    doc_type: str
    doc_period: int
    question_type: str
    question: str
    answer: str
    evidence: tuple[str, ...] = Field(default=())


def load_g_public(
    questions_path: Path,
    documents_path: Path,
    manifest: GPublicManifest,
    split: CompanySplit,
) -> list[PublicQuestion]:
    """Verified FinanceBench questions; NotVerifiedError when the manifest does not allow it."""
    check_manifest(manifest, {QUESTIONS_FILE: questions_path, DOCUMENTS_FILE: documents_path})
    documents = {d.doc_name: d for d in read_jsonl(documents_path, FinanceBenchDocument)}
    out: list[PublicQuestion] = []
    for record in read_jsonl(questions_path, FinanceBenchRecord):
        document = documents.get(record.doc_name)
        if document is None:
            raise ValueError(f"{record.financebench_id} cites unknown document {record.doc_name}")
        ticker = FINANCEBENCH_TICKERS.get(record.company)
        company = None if ticker is None else split.by_ticker(ticker)
        out.append(
            PublicQuestion(
                id=record.financebench_id,
                company=record.company,
                ticker=ticker,
                cik=None if company is None else company.cik,
                split="none" if company is None else company.split,
                in_scope=company is not None and document.doc_type.lower() in FILING_DOC_TYPES,
                doc_name=record.doc_name,
                doc_type=document.doc_type,
                doc_period=document.doc_period,
                question_type=record.question_type,
                question=record.question,
                answer=record.answer,
                evidence=tuple(e.evidence_text for e in record.evidence),
            )
        )
    return out
