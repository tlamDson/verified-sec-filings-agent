"""The cohort dashboard: activity of real users and of simulated accounts, side by side.

The two columns are never added together, and the simulated column is labelled test
traffic: simulated accounts are never reported as users (U1).
"""

from sec_agent.api.identity import Cohort
from sec_agent.api.store import CohortCounts
from sec_agent.eval.output import table

COLUMNS: tuple[Cohort, ...] = ("real", "simulated")
LABELS = {"users": "accounts"}
"""`users` is shown as `accounts`, since the simulated column counts test accounts."""
NOTE = "simulated = simulated accounts (test traffic), never counted as users"


def cohort_lines(counts: dict[Cohort, CohortCounts]) -> list[str]:
    rows = [["count", *COLUMNS]]
    for field in CohortCounts.model_fields:
        values = [str(getattr(counts[cohort], field)) for cohort in COLUMNS]
        rows.append([LABELS.get(field, field), *values])
    return [*table(rows), "", NOTE]
