"""The README results block: one table per metric family, rows straight from runs.csv."""

import re
from collections.abc import Sequence

from sec_agent.report.format import show_interval, show_value
from sec_agent.report.latest import latest_rows
from sec_agent.runs import RunRow

# family -> (title, caveat). Caveats hold no numbers: those come from the rows.
FAMILIES: dict[str, tuple[str, str]] = {
    "R1": (
        "Retrieval (R1)",
        "Questions on the test companies; intervals resample companies. `diff` rows are the "
        "difference between two systems on the same questions and `p` rows their paired test.",
    ),
    "L1": (
        "Latency (L1)",
        "Measured on the build machine's CPU, not on the deployed host.",
    ),
    "N1": (
        "Numeric answers (N1)",
        "Numeric questions on the test split, answer must match the XBRL value. b0 and b1 are "
        "baselines on the same local model; b2 is the agent. `p` rows are exact two-sided McNemar.",
    ),
    "A1": (
        "Agent scenarios (A1)",
        "Scenarios with named checks: tool and resolved arguments, traced figure, citation, "
        "faithfulness and text.",
    ),
    "S1": (
        "Safety (S1)",
        "G-red is synthetic: its filing passages are simulated, so these rows say nothing "
        "about real attackers.",
    ),
    "J1": (
        "Grader agreement (J1)",
        "Labels come from LLM raters, not human annotators; items they marked unsure are "
        "excluded. See `notes` in `runs.csv`.",
    ),
    "G1": (
        "Eval gate (G1)",
        "Planted mutations of the eval inputs that the CI gate must block, run over the "
        "committed results.",
    ),
    "LOAD": (
        "Load (simulated)",
        "Simulated accounts against a simulated model: nothing here measures answer quality.",
    ),
    "CHAOS": (
        "Chaos",
        "Worker kill during ingest, on the owner's machine.",
    ),
    "U1": (
        "Users",
        "Simulated accounts are test traffic and are never counted as users; "
        "real and simulated rows are separate.",
    ),
}

_FAMILY = re.compile(r"^[A-Z]+[0-9]*")


def family_of(metric: str) -> str:
    match = _FAMILY.match(metric)
    return match.group(0) if match else "other"


def _cohort_label(row: RunRow) -> str:
    return "" if row.cohort == "none" else f" ({row.cohort})"


_HEADER = ("Metric", "System", "Split", "n", "Value", "95% interval")
_RIGHT = {3, 4}


def _table(rows: Sequence[RunRow]) -> list[str]:
    """A padded markdown table, laid out the way the repository's formatter writes it."""
    body = [
        (
            f"`{row.metric}`{_cohort_label(row)}",
            row.system,
            row.split,
            str(row.n),
            show_value(row),
            show_interval(row),
        )
        for row in rows
    ]
    widths = [max(3, *(len(line[i]) for line in [_HEADER, *body])) for i in range(len(_HEADER))]

    def line(cells: Sequence[str]) -> str:
        padded = [
            cell.rjust(widths[i]) if i in _RIGHT else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        ]
        return "| " + " | ".join(padded) + " |"

    rule = [("-" * (w - 1) + ":") if i in _RIGHT else "-" * w for i, w in enumerate(widths)]
    return [line(_HEADER), "| " + " | ".join(rule) + " |", *(line(cells) for cells in body)]


def render_results(rows: Sequence[RunRow]) -> str:
    shown = latest_rows(rows)
    by_family: dict[str, list[RunRow]] = {}
    for row in shown:
        by_family.setdefault(family_of(row.metric), []).append(row)
    out = [
        "Every number below is a row of [`runs.csv`](runs.csv) (the latest row for each "
        "metric, system, split and cohort), printed by `sec-agent report sync`.",
        "",
    ]
    ordered = [name for name in FAMILIES if name in by_family]
    ordered += [name for name in by_family if name not in FAMILIES]
    for name in ordered:
        title, caveat = FAMILIES.get(name, (f"Other ({name})", ""))
        out += [f"#### {title}", ""]
        if caveat:
            out += [caveat, ""]
        out += [*_table(by_family[name]), ""]
    missing = [name for name in FAMILIES if name not in by_family]
    if missing:
        out += [
            "#### Not measured yet",
            "",
            "No row exists for: "
            + ", ".join(f"{name} ({FAMILIES[name][0]})" for name in missing)
            + ". Nothing is claimed for them.",
        ]
    return "\n".join(out).rstrip()
