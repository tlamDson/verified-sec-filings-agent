"""Fixed texts the guardrails answer with. They hold no figure, so they need no checking."""

ATTACK_REFUSED_TEXT = (
    "This question asks the assistant to set aside or reveal its instructions, so it was "
    "not answered. Ask about the figures or the text of a company's 10-K and 10-Q filings."
)
CANARY_BLOCKED_TEXT = (
    "The written answer was withheld because it repeated confidential instructions, which "
    "can mean the question or a filing passage tried to steer the assistant. Any figures "
    "and passages retrieved for your question are shown as returned by the tools. This is "
    "not investment advice."
)
ADVICE_DISCLAIMER = (
    "This is not investment advice: the figures above are historical, as reported in the "
    "company's filings, and say nothing about whether to buy, sell or hold."
)
ADVICE_DECLINED_TEXT = (
    "I can't give investment advice or forecast a stock. I can show the historical "
    "figures and filing text for a company: ask about its revenue, margins, cash flow or "
    "risk factors. This is not investment advice."
)
