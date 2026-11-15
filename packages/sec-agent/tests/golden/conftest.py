"""Fixtures for the golden-set tests: two real companies (recorded companyfacts) in a split.

Apple and NVIDIA come from the recorded SEC fixtures; the split around them is built by
hand for the tests (both in `test`, one sector), not the committed company split.
"""

import pytest
from golden_data import APPLE_CIK, NVIDIA_CIK, split_company
from xbrl_docs import APPLE, NVIDIA

from sec_agent.golden.gnum.candidates import GNumCompany
from sec_agent.golden.split import CompanySplit, SplitCompany
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize
from sec_agent.xbrl.versions import latest_versions


@pytest.fixture(scope="session")
def apple_company() -> SplitCompany:
    return split_company("AAPL", APPLE_CIK, "test", name="Apple Inc.")


@pytest.fixture(scope="session")
def nvidia_company() -> SplitCompany:
    return split_company("NVDA", NVIDIA_CIK, "test", name="Nvidia")


@pytest.fixture(scope="session")
def apple(apple_company: SplitCompany) -> GNumCompany:
    facts = latest_versions(normalize(parse_companyfacts(APPLE.read_bytes())).facts)
    return GNumCompany(company=apple_company, facts=tuple(facts))


@pytest.fixture(scope="session")
def nvidia(nvidia_company: SplitCompany) -> GNumCompany:
    facts = latest_versions(normalize(parse_companyfacts(NVIDIA.read_bytes())).facts)
    return GNumCompany(company=nvidia_company, facts=tuple(facts))


@pytest.fixture(scope="session")
def two_company_split(apple_company: SplitCompany, nvidia_company: SplitCompany) -> CompanySplit:
    others = [
        split_company("TRN1", 9_000_001, "train"),
        split_company("DEV1", 9_000_002, "dev"),
    ]
    return CompanySplit(
        seed=1, universe_sha256="0" * 64, companies=(apple_company, nvidia_company, *others)
    )
