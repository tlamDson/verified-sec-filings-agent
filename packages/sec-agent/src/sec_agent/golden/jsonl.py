"""JSON Lines files of Pydantic models: one compact object per line, UTF-8, LF endings."""

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ValidationError


def write_jsonl(path: Path, rows: Iterable[BaseModel]) -> int:
    """Write every row (replacing the file); return how many were written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(row.model_dump_json() + "\n")
            n += 1
    return n


def append_jsonl(path: Path, row: BaseModel) -> None:
    """Append one row and flush it, so an interrupted session keeps what it saved."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(row.model_dump_json() + "\n")
        handle.flush()


def read_jsonl[M: BaseModel](path: Path, model: type[M]) -> list[M]:
    """Every non-blank line as `model`; a missing file is empty. Errors name file and line."""
    if not path.exists():
        return []
    out: list[M] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                out.append(model.model_validate_json(line))
            except ValidationError as error:
                raise ValueError(f"{path.name}:{number}: {error}") from error
    return out
