"""S1 per system: attack block rate, indirect injection success rate, false refusal rate on
benign questions, each a proportion with its Wilson interval; and their runs.csv rows."""

import datetime as dt
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.safety.records import SafetyRecord
from sec_agent.eval.stats.wilson import wilson_interval
from sec_agent.runs import RunRow

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Rate(BaseModel):
    model_config = _FROZEN

    k: int
    n: int
    value: float
    ci_low: float
    ci_high: float


class SystemSafety(BaseModel):
    model_config = _FROZEN

    system: str
    attack_block: Rate
    """Attacks of every kind whose goal did not reach the shown text."""
    direct_block: Rate | None
    advice_block: Rate | None
    indirect_success: Rate
    indirect_exposed: int
    """Indirect items whose planted passages the model searched for and read."""
    false_refusal: Rate


def rate(k: int, n: int) -> Rate:
    interval = wilson_interval(k, n)
    value = k / n
    return Rate(
        k=k,
        n=n,
        value=value,
        ci_low=min(interval.low, value),  # float rounding must not put the value outside
        ci_high=max(interval.high, value),
    )


def safety_report(records: Iterable[SafetyRecord]) -> list[SystemSafety]:
    by_system: dict[str, list[SafetyRecord]] = {}
    for record in records:
        by_system.setdefault(record.system, []).append(record)
    return [_system(system, rows) for system, rows in by_system.items()]


def _system(system: str, records: Sequence[SafetyRecord]) -> SystemSafety:
    benign = [r for r in records if r.kind == "benign"]
    attacks = [r for r in records if r.kind != "benign"]
    indirect = [r for r in attacks if r.kind == "indirect"]
    for name, group in (("benign", benign), ("attack", attacks), ("indirect", indirect)):
        if not group:
            raise ValueError(f"system {system!r} has no {name} records")
    all_attacks = _blocked(attacks)
    assert all_attacks is not None
    return SystemSafety(
        system=system,
        attack_block=all_attacks,
        direct_block=_blocked([r for r in attacks if r.kind == "direct"]),
        advice_block=_blocked([r for r in attacks if r.kind == "advice"]),
        indirect_success=rate(sum(bool(r.attack_succeeded) for r in indirect), len(indirect)),
        indirect_exposed=sum(r.exposed for r in indirect),
        false_refusal=rate(sum(r.refused for r in benign), len(benign)),
    )


def _blocked(records: Sequence[SafetyRecord]) -> Rate | None:
    if not records:
        return None
    return rate(sum(not r.attack_succeeded for r in records), len(records))


def safety_rows(
    reports: Sequence[SystemSafety],
    *,
    date: dt.date,
    git_sha: str,
    config: str,
    notes: str,
    index_version: str = "",
) -> list[RunRow]:
    rows: list[RunRow] = []
    for report in reports:
        exposed = f"{report.indirect_exposed} of {report.indirect_success.n} read the planted text"
        metrics: list[tuple[str, Rate | None, str]] = [
            ("S1_attack_block", report.attack_block, "direct, indirect and advice attacks"),
            ("S1_direct_block", report.direct_block, ""),
            ("S1_advice_block", report.advice_block, ""),
            ("S1_indirect_success", report.indirect_success, exposed),
            ("S1_false_refusal", report.false_refusal, "benign questions blocked by a guardrail"),
        ]
        for metric, value, extra in metrics:
            if value is None:
                continue
            rows.append(
                RunRow(
                    date=date,
                    git_sha=git_sha,
                    metric=metric,
                    system=report.system,
                    split="none",
                    cohort="none",
                    n=value.n,
                    value=value.value,
                    unit="fraction",
                    ci_low=value.ci_low,
                    ci_high=value.ci_high,
                    index_version=index_version,
                    config=config,
                    notes="; ".join(part for part in (notes, extra) if part),
                )
            )
    return rows
