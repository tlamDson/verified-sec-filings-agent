"""Inputs are hashed with line endings normalised, so Windows and CI agree."""

from pathlib import Path

from sec_agent.eval.gate.digest import inputs_digest


def test_digest_ignores_crlf(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_bytes(b'{"x": 1}\n{"x": 2}\n')
    first = inputs_digest(tmp_path, ["a.jsonl"])
    (tmp_path / "a.jsonl").write_bytes(b'{"x": 1}\r\n{"x": 2}\r\n')
    assert inputs_digest(tmp_path, ["a.jsonl"]) == first


def test_digest_changes_with_content_names_and_order(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("1", "utf-8")
    (tmp_path / "b").write_text("1", "utf-8")
    one = inputs_digest(tmp_path, ["a"])
    assert inputs_digest(tmp_path, ["b"]) != one
    assert inputs_digest(tmp_path, ["a", "b"]) != inputs_digest(tmp_path, ["b", "a"])
    (tmp_path / "a").write_text("2", "utf-8")
    assert inputs_digest(tmp_path, ["a"]) != one
