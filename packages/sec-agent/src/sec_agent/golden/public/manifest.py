"""The G-public manifest: what was checked about an external set, and the files it pins.

The plan's rule: licence and answers are checked first; until both are, the set is not
used. A manifest records who-can-verify facts (source, licence, where it is stated, dates of
the checks) and pins each file by SHA-256, so a changed download is refused, not trusted.
"""

import datetime as dt
import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MANIFEST = Path("data/golden/g_public_manifest.json")


class NotVerifiedError(Exception):
    """The external set may not be used: a check is missing or a file is not the pinned one."""


class PinnedFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: int = Field(ge=0)


class GPublicManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    license: str
    license_source: str
    license_checked_on: dt.date | None
    license_note: str
    answers_checked_on: dt.date | None
    answers_note: str
    files: dict[str, PinnedFile]


def check_manifest(manifest: GPublicManifest, files: dict[str, Path]) -> None:
    """Raise NotVerifiedError unless both checks are recorded and every file matches its pin."""
    if manifest.license_checked_on is None:
        raise NotVerifiedError("the licence has not been checked")
    if manifest.answers_checked_on is None:
        raise NotVerifiedError(f"the answers have not been checked: {manifest.answers_note}")
    for name, path in files.items():
        pin = manifest.files.get(name)
        if pin is None:
            raise NotVerifiedError(f"{name} is not pinned in the manifest")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != pin.sha256:
            raise NotVerifiedError(f"{path} has sha256 {digest}, the manifest pins {pin.sha256}")


def read_manifest(path: Path) -> GPublicManifest:
    return GPublicManifest.model_validate_json(path.read_text("utf-8"))


def write_manifest(path: Path, manifest: GPublicManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2) + "\n", "utf-8", newline="\n")
