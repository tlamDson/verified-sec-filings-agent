"""The plan's chaos acceptance check (s-20) on a parsed k6 run.

"Kill 1 replica while 200 VU run: error rate under the limit, conversations resume." The
plan names no limit; this repository uses 5%, the same `rate<0.05` the k6 thresholds in
`infra/load/chat.js` hold, so the check does not depend on how k6 reports its thresholds.
"""

from sec_agent.chaos.k6_summary import (
    INTERRUPTED_RESUME_FAILED,
    RESUME_FAILED,
    TURN_FAILED,
    LoadSummary,
)

ERROR_RATE_LIMIT = 0.05


def breaches(summary: LoadSummary) -> list[str]:
    """One line per crossed limit; empty when the run passes. A rate at the limit fails."""
    found = [
        _breach(TURN_FAILED, summary.turns_failed, summary.turns),
        _breach(RESUME_FAILED, summary.resumes_failed, summary.resumes),
    ]
    if summary.interrupted:
        found.append(
            _breach(INTERRUPTED_RESUME_FAILED, summary.interrupted_failed, summary.interrupted)
        )
    return [line for line in found if line is not None]


def _breach(metric: str, failed: int, total: int) -> str | None:
    if total == 0:
        return f"{metric}: no sample, so the run does not show that conversations resume"
    rate = failed / total
    if rate < ERROR_RATE_LIMIT:
        return None
    return f"{metric}: {failed}/{total} = {rate:.4f}, not under the limit {ERROR_RATE_LIMIT}"
