"""Replace the text between two marker comments and leave the rest of the file alone."""

START = "<!-- results:start -->"
END = "<!-- results:end -->"


class MarkersMissingError(ValueError):
    """The file does not contain the start and end markers, in that order."""


def splice_block(text: str, block: str) -> str:
    start = text.find(START)
    end = text.find(END)
    if start < 0 or end < start:
        raise MarkersMissingError(f"expected {START} then {END}")
    head = text[: start + len(START)]
    return f"{head}\n{block.strip()}\n{text[end:]}"
