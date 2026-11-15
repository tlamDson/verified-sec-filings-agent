"""A system's structured reply to a G-num question, read from the end of its output.

The baselines are told to end with one JSON object (see `baselines.ANSWER_FORMAT`). The
reader takes the last JSON object in the output that has an "answer" key; anything else
is unparsed and graded wrong. Numbers are read as Decimal, never through float.
"""

import datetime as dt
import json
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from sec_agent.golden.gnum.models import AnswerUnit
from sec_agent.xbrl.calendar import FiscalPeriod

_REPLY = ConfigDict(frozen=True, extra="ignore")  # a model may add fields such as a citation


class NumberReply(BaseModel):
    model_config = _REPLY

    answer: Literal["number"]
    value: Decimal
    unit: AnswerUnit
    fiscal_year: int | None = None
    fiscal_period: FiscalPeriod | None = None
    period_end: dt.date | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _plain_number(cls, raw: object) -> object:
        """'$1,234.5' -> '1234.5'; words or scale suffixes stay and fail validation."""
        if isinstance(raw, str):
            return "".join(ch for ch in raw if ch not in "$,% \t")
        return raw

    @field_validator("value")
    @classmethod
    def _finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("value must be a finite number")
        return value

    @model_validator(mode="after")
    def _labels_together(self) -> Self:
        if (self.fiscal_year is None) != (self.fiscal_period is None):
            raise ValueError("give fiscal_year and fiscal_period together, or neither")
        return self


class CompanyReply(BaseModel):
    model_config = _REPLY

    answer: Literal["company"]
    ticker: str = Field(min_length=1)

    @field_validator("ticker")
    @classmethod
    def _upper(cls, ticker: str) -> str:
        return ticker.strip().upper()


class NotFoundReply(BaseModel):
    """The system says the filings do not hold the answer (E12)."""

    model_config = _REPLY

    answer: Literal["not_found"]


Reply = Annotated[NumberReply | CompanyReply | NotFoundReply, Field(discriminator="answer")]
_ADAPTER: TypeAdapter[Reply] = TypeAdapter(Reply)
_DECODER = json.JSONDecoder(parse_float=Decimal)


def parse_reply(output: str) -> Reply | None:
    last: dict[str, Any] | None = None
    start = output.find("{")
    while start != -1:
        try:
            obj, _ = _DECODER.raw_decode(output, start)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "answer" in obj:
            last = obj  # pyright: ignore[reportUnknownVariableType]
        start = output.find("{", start + 1)
    if last is None:
        return None
    try:
        return _ADAPTER.validate_python(last)
    except ValidationError:
        return None
