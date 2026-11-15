"""One server-sent event: a name line, one line of JSON, a blank line."""

from pydantic import BaseModel


def sse_event(name: str, payload: BaseModel) -> bytes:
    """Pydantic's JSON escapes every line break inside a string, so the data is one line
    and nothing in the payload can end the frame early."""
    return f"event: {name}\ndata: {payload.model_dump_json()}\n\n".encode()
