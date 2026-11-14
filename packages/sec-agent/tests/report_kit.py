"""Small RunRow builders for the report tests."""

from datetime import date

from sec_agent.runs import RunRow


def run(
    metric: str,
    system: str,
    value: float,
    *,
    unit: str = "fraction",
    n: int = 300,
    ci: tuple[float, float] | None = None,
    split: str = "test",
    cohort: str = "none",
    notes: str = "",
    sha: str = "abc1234",
) -> RunRow:
    return RunRow.model_validate(
        {
            "date": date(2026, 11, 14),
            "git_sha": sha,
            "metric": metric,
            "system": system,
            "split": split,
            "cohort": cohort,
            "n": n,
            "value": value,
            "unit": unit,
            "ci_low": ci[0] if ci else None,
            "ci_high": ci[1] if ci else None,
            "notes": notes,
        }
    )


def bullet_rows() -> list[RunRow]:
    return [
        run("N1", "b0", 0.15, ci=(0.114, 0.195)),
        run("N1", "b2", 0.75, ci=(0.698, 0.796)),
        run("A1", "rag", 0.16, n=50, ci=(0.083, 0.285)),
        run("A1", "agent", 0.78, n=50, ci=(0.648, 0.872)),
        run("S1_indirect_success", "none", 0.025, n=40, ci=(0.004, 0.129)),
        run("S1_indirect_success", "guarded", 0.0, n=40, ci=(0.0, 0.088)),
        run("R1_ndcg@10", "hybrid", 0.603, n=89, ci=(0.53, 0.673)),
        run("R1_ndcg@10", "hybrid+rerank-ft", 0.712, n=89, ci=(0.656, 0.77)),
    ]
