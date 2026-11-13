"""Hand-built companyfacts documents for edge cases the recorded fixtures do not show.

Shared by the XBRL tests; pytest puts this directory on sys.path (`pythonpath`).
These are synthetic: every value here is made up for a test, never reported as data.
"""

from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures" / "companyfacts"
NVIDIA = FIXTURES / "CIK0001045810.json"
APPLE = FIXTURES / "CIK0000320193.json"


def entry(
    end: str,
    val: float,
    accn: str,
    *,
    start: str | None = None,
    fy: int | None = 2023,
    fp: str | None = "FY",
    form: str = "10-K",
    filed: str = "2024-02-01",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }
    if start is not None:
        out["start"] = start
    return out


def document(
    tags: dict[str, dict[str, list[dict[str, Any]]]], *, cik: int = 1234
) -> dict[str, Any]:
    """A companyfacts document: `tags` maps us-gaap tag -> unit -> entries."""
    return {
        "cik": cik,
        "entityName": "Synthetic Test Corp",
        "facts": {"us-gaap": {tag: {"label": tag, "units": units} for tag, units in tags.items()}},
    }
