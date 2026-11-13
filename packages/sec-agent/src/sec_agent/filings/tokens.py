"""Token counting for chunk sizes.

The embedding model is chosen in s-05, so sizes here use a model-free proxy: one token per
run of word characters and one per punctuation mark. The tokenizer's name is part of the
chunk configuration, so switching to a model tokenizer later yields a new index_version.
"""

import re

TOKENIZER_NAME = "regex-word-punct-v1"
_TOKEN = re.compile(r"\w+|[^\w\s]")


def token_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _TOKEN.finditer(text)]


def count_tokens(text: str) -> int:
    return sum(1 for _ in _TOKEN.finditer(text))
