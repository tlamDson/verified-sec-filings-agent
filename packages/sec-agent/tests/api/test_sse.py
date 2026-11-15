"""Server-sent events as the API writes them."""

from pydantic import BaseModel

from sec_agent.api.sse import sse_event


class _Note(BaseModel):
    text: str
    count: int = 1


def test_an_event_is_its_name_then_one_line_of_json_then_a_blank_line() -> None:
    frame = sse_event("answer", _Note(text="ok"))
    assert frame == b'event: answer\ndata: {"text":"ok","count":1}\n\n'


def test_line_breaks_in_the_payload_never_break_the_frame() -> None:
    frame = sse_event("answer", _Note(text="first\nsecond\r\nthird"))
    assert frame.count(b"\n") == 3, "the name line, the data line and the blank line"
    assert frame.endswith(b"\n\n")
    assert b"\r" not in frame


def test_text_outside_ascii_is_sent_as_utf8() -> None:
    assert "Mondelēz".encode() in sse_event("answer", _Note(text="Mondelēz"))
