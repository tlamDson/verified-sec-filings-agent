"""A digest of the files a metric family is measured on, line endings normalised."""

import hashlib
from collections.abc import Iterable
from pathlib import Path


def inputs_digest(root: Path, paths: Iterable[str]) -> str:
    """SHA-256 over each path (as given, relative to `root`) and its bytes with CRLF read as
    LF, in the order given."""
    h = hashlib.sha256()
    for path in paths:
        data = (root / path).read_bytes().replace(b"\r\n", b"\n")
        h.update(f"{path}\0{len(data)}\0".encode())
        h.update(data)
    return h.hexdigest()
