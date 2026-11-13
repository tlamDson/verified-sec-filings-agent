"""Helpers shared by the golden-set tests; pytest puts this directory on sys.path."""

from pathlib import Path

from sec_agent.golden.split import SplitCompany

GOLDEN_FIXTURES = Path(__file__).parent / "fixtures" / "golden"

APPLE_CIK = 320193
NVIDIA_CIK = 1045810


def split_company(
    ticker: str, cik: int, split: str, sector: str = "Information Technology", name: str = ""
) -> SplitCompany:
    return SplitCompany.model_validate(
        {
            "ticker": ticker,
            "name": name or f"{ticker} Corp",
            "sector": sector,
            "cik": cik,
            "split": split,
        }
    )
