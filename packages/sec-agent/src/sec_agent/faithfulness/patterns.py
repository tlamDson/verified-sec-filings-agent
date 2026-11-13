"""The text patterns `scan` reads: what holds digits but is not a figure, and figures.

Order matters: citation keys and dates hold digits of their own, so they are read (and
masked) before anything else; standalone years after every other digit pattern.
"""

import re

_I = re.IGNORECASE
_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
MONTH_NUMBERS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

ACCESSION = r"\d{10}-\d{2}-\d{6}"
BRACKET = re.compile(r"\[([^\[\]]*)\]")
CITATION_KEY = re.compile(rf"(?<![\w-]){ACCESSION}(?:/[^\s;,\[\]]*)?(?![\w-])")
"""An accession and whatever follows it up to a separator: `acc`, `acc/mdna/3`, and also
malformed keys such as `acc/mdna`, read whole so they are judged as written."""

MONTH_DAY_YEAR = re.compile(
    rf"\b(?P<month>{_MONTHS})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})\b", _I
)
ISO_DATE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
US_DATE = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b")
MONTH_YEAR = re.compile(rf"\b(?:{_MONTHS})\.?\s+(?P<year>\d{{4}})\b", _I)
FISCAL_YEAR = re.compile(
    r"\bFY\s?'?(?P<year>\d{4}|\d{2})\b|\bfiscal\s+(?:year\s+)?(?P<long>\d{4})\b", _I
)
YEAR = re.compile(
    r"(?<![\d,.$])\b(?P<year>(?:19|20)\d{2})\b(?![,.]\d)"
    r"(?!\s?(?:%|percent|per\s?cent|thousand|million|billion|trillion|bn\b|mm\b|[kmbtx]\b"
    r"|times|shares?|dollars|usd))",
    _I,
)
"""A bare year: four digits 1900-2099 with no separator, currency, scale or unit."""

NOT_FIGURES = tuple(
    re.compile(p, _I)
    for p in (
        r"https?://\S+",
        rf"\b{ACCESSION}\b",
        r"\bCIK\s*:?\s*\d+\b",
        r"\b(?:10-K|10-Q|8-K|20-F|40-F|S-1|DEF\s?14A)(?:/A)?\b",
        r"\bItems?\s+\d+[A-C]?(?:\s*(?:,|and|&|-|\u2013|to)\s*\d+[A-C]?)*\b",
        r"\b[QH][1-4]\b",
        r"\b\d+[-\s](?:month|week|day|year|quarter)s?\b",
        r"(?:\bS&P|\bFortune|\bRussell|\bNasdaq)[\s-]*\d+\b",
    )
)
"""Forms, items, quarters, durations, index names, links and ids: digits, not figures."""

NUMBER = re.compile(
    r"(?<![\w.])(?<![A-Za-z]-)"
    r"(?P<open>\()?"
    r"(?:(?P<minus>[-\u2212\u2013])(?=[$\d.]|US\$|USD))?"
    r"(?P<currency>US\$|\$|USD\s?)?"
    r"(?P<digits>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<ordinal>(?:st|nd|rd|th)\b)?"
    r"(?P<close>\))?"
    r"(?:\s?(?P<scale>thousand|million|billion|trillion|bn|mm|k|m|b|t)\b)?",
    _I,
)
STATED_SCALE = re.compile(r"\bin\s+(?P<scale>thousands|millions|billions)\b", _I)
"""A table heading's scale: "(in millions, except per share amounts)"."""

SCALES = {
    "thousand": 3,
    "k": 3,
    "million": 6,
    "mm": 6,
    "m": 6,
    "billion": 9,
    "bn": 9,
    "b": 9,
    "trillion": 12,
    "t": 12,
    "thousands": 3,
    "millions": 6,
    "billions": 9,
}

PERCENT_AFTER = re.compile(r"\s?(?:%|percent\b|per\s?cent\b|percentage\s+points?\b|pp\b)", _I)
TIMES_AFTER = re.compile(r"(?:x(?!\w)|\s?times\b)", _I)
PER_SHARE_AFTER = re.compile(r"\s*(?:per|a|/)\s*(?:diluted\s+|basic\s+|common\s+)?share\b", _I)
SHARES_AFTER = re.compile(r"\s+(?:(?!per\b)[a-z]+\s+){0,2}shares?\b", _I)
DOLLARS_AFTER = re.compile(r"\s+(?:dollars|usd)\b", _I)
