"""The patterns the guardrails match, each named so a decision says which rule fired.

They are written for the shapes of attack G-red is built from: orders to drop earlier
instructions, requests for the hidden prompt, role-play that removes rules, and text
addressed to an AI. Ordinary research wording ("ignore the 10-Q", "instructions to
shareholders", "export restrictions") must not match; the S1 false-refusal rate measures
how far that holds. Filing text is matched one sentence at a time, so `^` starts one.
"""

import re

Rules = tuple[tuple[str, re.Pattern[str]], ...]

_I = re.IGNORECASE
_PRIOR = (
    r"(?:all\s+|any\s+|the\s+|your\s+|of\s+your\s+|my\s+)*"
    r"(?:previous|prior|above|earlier|preceding|initial|system)"
)
_ORDERS = (
    r"(?:instructions?|rules|prompts?|directions|guidelines|constraints|directives|guardrails)"
)
_AI = (
    r"(?:ai|a\.i\.|assistants?|language\s+models?|llms?|chat\s*bots?|ai\s+models?|"
    r"automated\s+(?:systems?|readers?|agents?))"
)


def _rule(name: str, *parts: str) -> tuple[str, re.Pattern[str]]:
    return name, re.compile("".join(parts), _I)


ATTACK_TEXT: Rules = (
    _rule("ignore_instructions", rf"\b(?:ignore|disregard|forget|bypass)\s+{_PRIOR}\s+{_ORDERS}"),
    _rule(
        "forget_rules",
        r"\b(?:ignore|disregard|forget|override|bypass|drop|abandon)\s+(?:all\s+)?(?:of\s+)?",
        rf"your\s+(?:\w+\s+)?{_ORDERS}",
    ),
    _rule(
        "reveal_prompt",
        r"\b(?:reveal|show|print|repeat|output|display|tell\s+me|give\s+me|share|leak|dump|",
        r"recite|write\s+out)\b[^.?!\n]{0,40}?\b(?:system\s+prompt|hidden\s+prompt|",
        r"initial\s+prompt|secret\s+prompt|(?:system|hidden|secret|original|initial)\s+",
        r"(?:instructions|rules|message)|instructions\s+you\s+(?:were|have\s+been)\s+given|",
        r"your\s+(?:instructions|prompt|rules|canary|marker))",
    ),
    _rule(
        "role_override",
        r"\byou\s+are\s+now\s+(?:dan\b|an?\s+(?:ai|assistant|model)\s+(?:without|with\s+no)\b|",
        r"(?:in\s+)?(?:developer|god|jailbreak|unrestricted|unfiltered)\b|free\b|no\s+longer\b)",
    ),
    _rule("jailbreak_mode", r"\b(?:developer|god|dan|jailbreak|jailbroken)\s+mode\b"),
    _rule(
        "no_restrictions",
        r"\b(?:pretend|imagine|act\s+as\s+if|behave\s+as\s+if)\b[^.?!\n]{0,30}?",
        r"\b(?:no|without)\s+(?:rules|restrictions|limits|guidelines|filters|guardrails)",
    ),
    _rule(
        "unrestricted_persona",
        r"\b(?:act|respond|answer)\s+as\s+(?:an?\s+)?(?:unfiltered|unrestricted|uncensored|evil|rogue)\b",
    ),
    _rule(
        "override_safety",
        r"\b(?:override|disable|turn\s+off|switch\s+off|bypass)\s+(?:your\s+(?:safety|",
        r"guardrails?|filters?|content\s+polic(?:y|ies)|restrictions|rules)|(?:the\s+)?",
        r"(?:guardrails?|content\s+polic(?:y|ies)|safety\s+(?:rules|filters)))",
    ),
    _rule("new_instructions", r"\bnew\s+(?:system\s+)?instructions\s*:"),
)
"""Attack shapes that are never ordinary filing wording either."""

ATTACK: Rules = (
    *ATTACK_TEXT,
    _rule("hidden_prompt", r"\b(?:system|hidden|secret)\s+prompt\b"),
    _rule("jailbreak", r"\bjailbr(?:eak|oken)"),
)
"""A direct attack: the question tries to remove or read the rules. "Jailbreak" alone is
an attack in a question, but filing text may use it of phones."""

ADDRESSED_TO_AI: Rules = (
    _rule(
        "note_to_ai",
        r"\b(?:note|message|instructions?|attention|notice|reminder|directive)s?\s+(?:to|for)\s+",
        rf"(?:the\s+|any\s+|all\s+)?{_AI}\b",
    ),
    _rule(
        "ai_vocative",
        r"^\W*(?:(?:dear|hey|hello|attention)\s+)?(?:the\s+)?(?:ai|assistant|llm|chatbot|",
        r"language\s+model|gpt)(?:\s+(?:assistant|model|system|agent))?s?\s*[:,]|",
        r"\b(?:ai|assistant|llm|model|chatbot)s?\s+(?:reading|processing|summari[sz]ing)\s+this",
    ),
    _rule("if_you_are_ai", rf"\bif\s+you\s+are\s+(?:an?\s+)?(?:{_AI}|automated)"),
    _rule(
        "when_summarising",
        r"\bwhen\s+(?:summari[sz]ing|answering|responding|reading|processing|quoting)\s+",
        r"(?:this|these|the\s+following)",
    ),
    _rule(
        "reply_with",
        r"\b(?:respond|reply|answer)\s+(?:only\s+with|with\s+(?:only\s+)?(?:the\s+)?(?:word|",
        r"phrase|text|string|token|code|marker))\b|\b(?:end|begin|start|finish|close)\s+",
        r"(?:your|the|each|every)\s+(?:answer|response|reply|output|summary)\s+with\b",
    ),
    _rule(
        "include_marker",
        r"\b(?:include|insert|append|add|mention|output|write|print|say)\s+(?:the\s+)?",
        r"(?:following|confidential|secret|hidden|special)\s+(?:marker|token|code|phrase|",
        r"word|string|text)",
    ),
    _rule(
        "tell_user_to_trade",
        r"\b(?:tell|advise|urge|instruct|encourage)\s+(?:the\s+)?(?:user|users|reader|readers|",
        r"investors?|customers?)\s+to\s+(?:buy|sell|purchase|short|invest|dump|acquire)",
    ),
    _rule("system_override", r"\bsystem\s+(?:override|note|instruction|prompt)\b"),
    _rule(
        "do_not_mention",
        r"\b(?:do\s+not|don't|never)\s+(?:mention|reveal|disclose|tell)\s+(?:the\s+user|anyone|",
        r"this\s+instruction)",
    ),
)
"""Filing text that speaks to the AI reading it rather than to investors."""

INJECTION: Rules = (*ATTACK_TEXT, *ADDRESSED_TO_AI)
"""What quarantine removes from filing text: an attack shape, or text addressed to an AI."""

ADVICE_REQUEST: Rules = (
    _rule(
        "should_i_trade",
        r"\b(?:should|shall|must|would|could)\s+(?:i|we|you|one)\s+(?:\w+\s+)?",
        r"(?:buy|sell|hold|short|invest|purchase|keep|dump|add\s+to|exit|trim)\b",
    ),
    _rule(
        "good_investment",
        r"\b(?:good|great|bad|smart|safe|wise|solid)\s+(?:investment|buy|stock\s+to\s+",
        r"(?:buy|own)|time\s+to\s+(?:buy|sell|invest))",
    ),
    _rule("worth_buying", r"\bworth\s+(?:buying|investing|owning|holding)\b"),
    _rule(
        "trade_or", r"\b(?:buy|sell|hold)\s+or\s+(?:buy|sell|hold)\b|\b(?:buy|sell|hold)\s+rating\b"
    ),
    _rule("price_target", r"\bprice\s+targets?\b|\btarget\s+price\b"),
    _rule(
        "price_move",
        r"\b(?:will|would|going\s+to)\b[^.?!\n]{0,40}?\b(?:stock|shares?|share\s+price)\b",
        r"[^.?!\n]{0,20}?\b(?:go\s+up|go\s+down|rise|fall|drop|climb|rally|crash|increase|",
        r"decrease|outperform|underperform|double)",
    ),
    _rule(
        "recommend_stock",
        r"\b(?:recommend|suggest|pick)\b[^.?!\n]{0,30}?\b(?:stocks?|shares|investments?|portfolio)\b",
    ),
    _rule("put_money_in", r"\bput\s+(?:my|our)\s+(?:money|savings)\s+in(?:to)?\b"),
)
"""The question asks for advice, a price target or a forecast of the stock (E9)."""

ADVICE_STATEMENT: Rules = (
    _rule(
        "you_should_trade",
        r"\b(?:you|investors|one|we)\s+(?:should|must|ought\s+to|might\s+want\s+to|may\s+want\s+to)",
        r"\s+(?:\w+\s+)?(?:(?:buy|sell|hold|short|invest|add|exit|dump)(?:ing)?|purchas(?:e|ing)|",
        r"accumulat(?:e|ing)|trim(?:ming)?|stay\s+invested|hang\s+on)\b",
    ),
    _rule(
        "i_would_trade",
        r"\b(?:i['’]d|i\s+would|i['’]ll|i\s+will)\s+(?:still\s+|just\s+|probably\s+)?",  # noqa: RUF001
        r"(?:hold|buy|sell|short|dump|trim|accumulate|keep\s+holding|stay\s+invested)\b(?![-\w])",
    ),
    _rule(
        "i_recommend",
        r"\b(?:i|we)(?:['’]d|\s+would|\s+strongly)?\s+(?:strongly\s+)?",  # noqa: RUF001
        r"(?:recommend|suggest|advise|rate)\b",
        r"[^.?!\n]{0,30}?\b(?:buy|sell|hold|short|invest|purchas|accumulat|position)",
    ),
    _rule(
        "rating",
        r"\b(?:strong\s+)?(?:buy|sell|hold)\s+(?:rating|recommendation)\b|\bstrong\s+(?:buy|sell)\b",
        r"|\b(?:is|remains|stays|rated|rate\s+it)\s+(?:still\s+)?an?\s+(?:strong\s+)?",
        r"(?:buy|sell|hold)\b(?![-\w])",
    ),
    _rule(
        "good_investment",
        r"\b(?:is|looks|seems|remains|makes)\s+(?:like\s+)?(?:an?\s+)?(?:very\s+)?(?:good|great|",
        r"excellent|solid|attractive|bad|poor|compelling)\s+(?:investment|buy|stock|pick)",
    ),
    _rule("price_target", r"\bprice\s+targets?\b|\btarget\s+price\b"),
    _rule(
        "stock_forecast",
        r"\b(?:stock|shares?|share\s+price)\b[^.?!\n]{0,30}?\b(?:will|is\s+(?:likely|expected|",
        r"going)\s+to|should)\s+(?:likely\s+)?(?:go\s+up|go\s+down|rise|fall|climb|rally|drop|",
        r"outperform|underperform|double|increase|decrease)",
    ),
    _rule("buy_now", r"\b(?:buy|sell)\s+(?:\w+\s+){0,2}(?:now|today|immediately)\b"),
    _rule(
        "trade_imperative",
        r"^\W*(?:consider\s+(?:buying|selling|shorting|purchasing|holding)|(?:keep|continue)\s+",
        r"holding|stay\s+invested|hang\s+on|(?:don['’]t|do\s+not)\s+(?:buy|sell|short|dump)|",  # noqa: RUF001
        r"(?:(?:go\s+ahead\s+and|just|so|then)\s+)?(?:buy|sell|short|purchase|accumulate|dump|",
        r"hold))\b(?![-\w])",
        r"(?!\s+(?:of|obligations?|commitments?|orders?|prices?|agreements?|side|volumes?|harmless)\b)",
    ),
)
"""A sentence of the answer gives advice or forecasts the stock (E9)."""


def first_match(text: str, rules: Rules) -> str | None:
    """The name of the first rule that matches `text`; None when none does."""
    for name, pattern in rules:
        if pattern.search(text):
            return name
    return None
