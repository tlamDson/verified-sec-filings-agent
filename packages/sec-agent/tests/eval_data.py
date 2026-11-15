"""Simulated G-num questions for the eval tests; pytest puts this directory on sys.path.

Every question and answer here is made up: the companies are the simulated SIMW and SIMB.
"""

import datetime as dt
import hashlib
from decimal import Decimal

from sec_agent.golden.gnum.models import CompanyAnswer, NumberAnswer, NumQuestion, QuestionType

SIMW_CIK = 9999999999
SIMB_CIK = 9999999998
FY_END = dt.date(2024, 1, 28)  # an off-calendar fiscal year (E1)
FY_START = dt.date(2023, 1, 30)


def qid(name: str) -> str:
    return "gnum-" + hashlib.sha256(name.encode()).hexdigest()[:16]


def number_question(
    name: str,
    value: str,
    unit: str = "USD",
    qtype: QuestionType = "value",
    *,
    period_start: dt.date | None = FY_START,
) -> NumQuestion:
    return NumQuestion.model_validate(
        {
            "id": qid(name),
            "split": "test",
            "qtype": qtype,
            "question": f"What did Simulated Widgets Inc. (SIMW) report as {name} for FY2024?",
            "tickers": ("SIMW",),
            "ciks": (SIMW_CIK,),
            "concept": name,
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "period_kind": "annual",
            "answer": NumberAnswer.model_validate(
                {
                    "value": Decimal(value),
                    "unit": unit,
                    "period_start": period_start,
                    "period_end": FY_END,
                }
            ),
            "sources": (),
            "index_version": "v-test",
        }
    )


def peer_question(name: str, winner: str = "SIMB") -> NumQuestion:
    return NumQuestion.model_validate(
        {
            "id": qid(f"peer-{name}"),
            "split": "test",
            "qtype": "peer_comparison",
            "question": f"Which company reported the higher {name}: SIMW or SIMB?",
            "tickers": ("SIMW", "SIMB"),
            "ciks": (SIMW_CIK, SIMB_CIK),
            "concept": name,
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "period_kind": "annual",
            "answer": CompanyAnswer(ticker=winner, cik=SIMB_CIK if winner == "SIMB" else SIMW_CIK),
            "sources": (),
            "index_version": "v-test",
        }
    )
