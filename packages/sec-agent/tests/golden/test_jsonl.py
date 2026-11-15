"""JSON Lines of Pydantic models: one object per line, errors name the line."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from sec_agent.golden.jsonl import append_jsonl, read_jsonl, write_jsonl


class Row(BaseModel):
    name: str
    n: int


def test_write_append_read_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    write_jsonl(path, [Row(name="a", n=1)])
    append_jsonl(path, Row(name="b", n=2))
    assert read_jsonl(path, Row) == [Row(name="a", n=1), Row(name="b", n=2)]
    assert path.read_text("utf-8") == '{"name":"a","n":1}\n{"name":"b","n":2}\n'


def test_read_skips_blank_lines_and_names_a_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"name":"a","n":1}\n\n{"name":"b"}\n', "utf-8")
    with pytest.raises(ValueError, match=r"rows\.jsonl:3"):
        read_jsonl(path, Row)


def test_read_of_a_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "none.jsonl", Row) == []
