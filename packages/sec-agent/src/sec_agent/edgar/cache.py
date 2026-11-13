"""Raw cache: SEC response bodies on disk, keyed by URL, so re-runs send no request.

Layout: `<root>/<host>/<sha256[:2]>/<sha256><suffix>`, where the hash covers the full URL
(query string included) and the suffix comes from the URL path (`.json`, `.htm`, ...).
Writes go to a temporary file in the same directory and are renamed into place, so a
crash never leaves a half-written body behind.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,8}")
_HOST = re.compile(r"[a-z0-9.-]+")


class RawCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, url: str) -> Path:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if not _HOST.fullmatch(host):
            raise ValueError(f"cannot cache a URL without a plain host: {url!r}")
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = PurePosixPath(parts.path).suffix
        if not _SUFFIX.fullmatch(suffix):
            suffix = ""
        return self.root / host / digest[:2] / f"{digest}{suffix}"

    def get(self, url: str) -> bytes | None:
        try:
            return self.path_for(url).read_bytes()
        except FileNotFoundError:
            return None

    def put(self, url: str, body: bytes) -> Path:
        path = self.path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path
