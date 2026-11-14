"""advice_rule: which rule, if any, finds investment advice or a stock forecast in one
sentence of an answer (E9).

A sentence is read clause by clause (split at ";", a dash, "but", "however", "though",
"although"), so "I can't give advice, but you should buy NVDA" is caught in its second
clause. A clause that declines ("I cannot provide investment advice or recommend whether
you should buy") is not advice, whatever trade words it names. Historical wording
("Purchase obligations", "Apple holds", "Short-term investments", "Revenue could
decline") must not match.
"""

import re

from sec_agent.guardrails.patterns import Rules, first_match, rule

_TRADE = (
    r"(?:(?:buy|sell|hold|short|invest|add|exit|dump)(?:ing)?|purchas(?:e|ing)|"
    r"accumulat(?:e|ing)|trim(?:ming)?)"
)
_FUTURE = (
    r"(?:will|would|could|may|might|should|can|(?:is|are)\s+(?:likely|expected|poised|set|"
    r"going|bound)\s+to)"
)
_MOVE = (
    r"(?:go\s+up|go\s+down|rise|fall|climb|rally|drop|soar|surge|jump|plunge|tumble|crash|"
    r"rebound|outperform|underperform|double|triple|increase|decrease|reach|hit)"
)
_STOCK = r"(?<![-\w])(?:stock|shares?|share\s+price|stock\s+price)\b(?!-)"

ADVICE_STATEMENT: Rules = (
    rule(
        "you_should_trade",
        r"\b(?:you|investors|one|we)\s+(?:should|must|ought\s+to|need\s+to|might\s+want\s+to|",
        r"may\s+want\s+to|would\s+do\s+well\s+to)",
        rf"\s+(?:\w+\s+)?(?:{_TRADE}|stay\s+invested|hang\s+on)\b",
    ),
    rule(
        "you_could_trade",
        r"\b(?:you|investors)\s+(?:might|could|may\s+wish\s+to)\s+(?:also\s+)?(?:consider\s+)?",
        rf"{_TRADE}\b",
    ),
    rule(
        "i_would_trade",
        r"\b(?:i['’]d|i\s+would|i['’]ll|i\s+will)\s+(?:still\s+|just\s+|probably\s+)?",  # noqa: RUF001
        r"(?:hold|buy|sell|short|dump|trim|accumulate|keep\s+holding|stay\s+invested)\b(?![-\w])",
    ),
    rule(
        "i_would_not_trade",
        r"\bi\s+(?:wouldn['’]t|would\s+not)\s+(?:\w+\s+)?(?:buy|sell|hold|short|touch|",  # noqa: RUF001
        r"recommend\s+(?:buying|selling|holding|shorting))\b",
    ),
    rule(
        "i_recommend",
        r"\b(?:i|we)(?:['’]d|\s+would|\s+strongly)?\s+(?:strongly\s+)?",  # noqa: RUF001
        r"(?:recommend|suggest|advise|rate)\b",
        r"[^.?!\n]{0,30}?\b(?:buy|sell|hold|short|invest|purchas|accumulat|position)",
    ),
    rule(
        "rating",
        r"\b(?:strong\s+)?(?:buy|sell|hold)\s+(?:rating|recommendation)\b|\bstrong\s+(?:buy|sell)\b",
        r"|\b(?:is|remains|stays|rated|rate\s+it)\s+(?:still\s+)?an?\s+(?:strong\s+)?",
        r"(?:buy|sell|hold)\b(?![-\w])",
    ),
    rule(
        "labelled_call",
        r"\b(?:recommendation|verdict|rating|advice|call|bottom\s+line)",
        r"(?:\s*\*{0,2}\s*:\s*\*{0,2}|\s+(?:is|would\s+be))\s*(?:to\s+|an?\s+)?(?:strong\s+)?",
        r"(?:buy|sell|hold|accumulate|overweight|underweight|outperform)\b(?![-\w])",
    ),
    rule(
        "good_investment",
        r"\b(?:is|looks|seems|remains|makes)\s+(?:like\s+)?(?:an?\s+)?(?:very\s+)?(?:good|great|",
        r"excellent|solid|attractive|bad|poor|compelling)\s+(?:investment|buy|stock|pick)",
    ),
    rule(
        "good_time",
        r"\b(?:good|great|right|best|ideal|perfect|bad|wrong)\s+(?:time|moment|entry\s+point|",
        rf"opportunity)\s+to\s+(?:{_TRADE}|get\s+in|get\s+out|take\s+profits)\b",
        r"|\bbuying\s+opportunit(?:y|ies)\b",
    ),
    rule(
        "worth_trading",
        r"\b(?:worth|wise|smart|prudent|sensible|advisable|a\s+good\s+idea|makes\s+sense)\s+",
        rf"(?:to\s+)?(?:{_TRADE}|own(?:ing)?)\b",
    ),
    rule(
        "valuation_call",
        r"\b(?:is|are|looks?|seems?|appears?|remains?|stays?)\s+(?:\w+\s+)?(?:undervalued|",
        r"overvalued|underpriced|overpriced|a\s+bargain|a\s+steal|attractively\s+(?:priced|valued))",
        r"\b|\b(?:looks?|seems?|appears?)\s+(?:\w+\s+)?(?:cheap|expensive)\b",
    ),
    rule(
        "sentiment",
        r"\b(?:bullish|bearish)\b|\b(?:significant|substantial|limited|more|further|big|huge|",
        r"meaningful)\s+(?:upside|downside)\b|\bupside\s+(?:potential|from\s+here)\b",
    ),
    rule("price_target", r"\bprice\s+targets?\b|\btarget\s+price\b"),
    rule(
        "stock_forecast",
        rf"{_STOCK}[^.?!\n]{{0,30}}?\b{_FUTURE}\s+(?:likely\s+)?{_MOVE}\b",
        rf"|\b(?:expect|predict|forecast|anticipate)\s+(?:the\s+|its\s+)?{_STOCK}\s+to\s+{_MOVE}\b",
    ),
    rule(
        "market_forecast",
        rf"\b{_FUTURE}\s+(?:likely\s+|continue\s+to\s+)?(?:outperform|underperform|beat\s+the\s+",
        r"market|rally|soar|skyrocket)\b",
    ),
    rule("buy_now", r"\b(?:buy|sell)\s+(?:\w+\s+){0,2}(?:now|today|immediately)\b"),
    rule(
        "trade_imperative",
        r"^\W*(?:consider\s+(?:buying|selling|shorting|purchasing|holding)|(?:keep|continue)\s+",
        r"holding|stay\s+invested|hang\s+on|(?:don['’]t|do\s+not)\s+(?:buy|sell|short|dump)|",  # noqa: RUF001
        r"load\s+up|go\s+(?:long|short)|take\s+profits?|lock\s+in\s+(?:gains|profits)|",
        r"stay\s+away\s+from|get\s+out\s+of|buy\s+the\s+dip|add\s+(?:\S+\s+){0,3}?to\s+(?:your|",
        r"the|a)\s+portfolio|avoid\s+(?:(?-i:[A-Z]{2,5})|(?:the|this|its|their)\s+(?:stock|shares))|",
        r"(?:(?:go\s+ahead\s+and|just|so|then)\s+)?(?:buy|sell|short|purchase|accumulate|dump|",
        r"hold))\b(?![-\w])",
        r"(?!\s+(?:of|obligations?|commitments?|orders?|prices?|agreements?|side|volumes?|harmless)\b)",
    ),
)
"""A clause of the answer gives advice or forecasts the stock (E9)."""

DECLINE = re.compile(
    r"\b(?:cannot|can['’]?t|can\s+not|won['’]t|will\s+not|(?:am|['’]m)\s+(?:not\s+able|unable)\s+"  # noqa: RUF001
    r"to|unable\s+to|not\s+able\s+to|not\s+in\s+a\s+position\s+to|(?:must\s+)?decline\s+to)\s+"
    r"(?:\w+\s+){0,2}?(?:provide|give|offer|make|share|recommend|advise|predict|forecast|tell|"
    r"say|determine|comment|speculate|assess|judge)\b"
    r"|\b(?:do\s+not|don['’]t)\s+(?:\w+\s+)?(?:provide|give|offer|make|predict|forecast|"  # noqa: RUF001
    r"speculate|comment)\b"
    r"|\bnot\s+(?:investment|financial)\s+advice\b|\bnot\s+a\s+recommendation\b",
    re.IGNORECASE,
)
"""A clause that declines to advise or forecast, rather than doing it."""

_CLAUSE = re.compile(
    r";|\s[-–—]\s|,?\s+\b(?:but|however|though|although)\b,?|^\W*however\b,?",  # noqa: RUF001
    re.IGNORECASE,
)


def advice_rule(sentence: str) -> str | None:
    """The first advice rule a clause of `sentence` matches; None when no clause gives
    advice."""
    for clause in _CLAUSE.split(sentence):
        if not clause.strip() or DECLINE.search(clause):
            continue
        if (name := first_match(clause.strip(), ADVICE_STATEMENT)) is not None:
            return name
    return None
