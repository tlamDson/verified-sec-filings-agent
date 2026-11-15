"""Filing HTML to text blocks: one block per paragraph, heading, line, or table row.

Hidden content is dropped: `script`, `style`, `head`, the inline-XBRL `ix:header`, and any
element styled `display:none` (where inline XBRL keeps its hidden facts). Table cells of a
row join with a space, so a table of contents row reads "Item 1A. Risk Factors 12" and a
financial row reads "Net sales $ 1,234". Page numbers and "Table of Contents" back-links,
which filings repeat at every page break, are dropped.
"""

import re
from html.parser import HTMLParser

_BLOCK_TAGS = frozenset(
    {
        "address", "article", "blockquote", "body", "br", "caption", "center", "dd", "div",
        "dl", "dt", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
        "ol", "p", "pre", "section", "table", "tbody", "tfoot", "thead", "tr", "ul",
    }
)  # fmt: skip
_CELL_TAGS = frozenset({"td", "th"})
_SKIP_TAGS = frozenset({"head", "ix:header", "noscript", "script", "style", "template"})
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)

_WHITESPACE = re.compile(r"\s+")
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.IGNORECASE)
_NOISE = re.compile(r"(?:page\s+)?\d{1,3}|table\s+of\s+contents", re.IGNORECASE)


def decode_html(raw: bytes) -> str:
    """UTF-8 when valid (inline XBRL is UTF-8), else Windows-1252 (older EDGAR HTML)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def html_blocks(html: str | bytes) -> list[str]:
    text = decode_html(html) if isinstance(html, bytes) else html
    parser = _BlockParser()
    parser.feed(text)
    parser.close()
    return parser.blocks


def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
    return any(name == "style" and value and _HIDDEN_STYLE.search(value) for name, value in attrs)


class _BlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._parts: list[str] = []
        # Open tags inside the hidden element being skipped (its own tag first). An end tag
        # closes back to its last match, so unclosed tags inside cannot hide the rest.
        self._skipping: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skipping:
            if tag not in _VOID_TAGS:
                self._skipping.append(tag)
            return
        if tag in _SKIP_TAGS or _is_hidden(attrs):
            if tag not in _VOID_TAGS:
                self._skipping.append(tag)
            return
        self._boundary(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._skipping and tag not in _SKIP_TAGS and not _is_hidden(attrs):
            self._boundary(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skipping:
            if tag in self._skipping:
                last = len(self._skipping) - 1 - self._skipping[::-1].index(tag)
                del self._skipping[last:]
            return
        self._boundary(tag)

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _boundary(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._flush()
        elif tag in _CELL_TAGS:
            self._parts.append(" ")

    def _flush(self) -> None:
        text = _ZERO_WIDTH.sub("", "".join(self._parts))
        text = _WHITESPACE.sub(" ", text).strip()
        self._parts.clear()
        if text and not _NOISE.fullmatch(text):
            self.blocks.append(text)
