"""`sec-agent eval mutations` prints "blocked N/10" and records G1."""

from collections.abc import Callable
from pathlib import Path

import pytest

from sec_agent.cli import main
from sec_agent.eval.gate import mutations_cli
from sec_agent.eval.gate.mutate import MutationResult, Outcome
from sec_agent.runs import read_runs


def _fake(outcomes: list[Outcome]) -> Callable[..., list[MutationResult]]:
    def run(*_args: object, **_kw: object) -> list[MutationResult]:
        return [MutationResult(id=f"m{i}", outcome=o, detail="x") for i, o in enumerate(outcomes)]

    return run


def test_all_blocked_exits_zero_and_records_g1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mutations_cli, "run_mutations", _fake(["blocked"] * 10))
    runs = tmp_path / "runs.csv"
    assert main(["eval", "mutations", "--record", str(runs), "--git-sha", "abc1234"]) == 0
    assert "blocked 10/10" in capsys.readouterr().out
    (row,) = read_runs(runs)
    assert (row.metric, row.system, row.n, row.value, row.cohort, row.split) == (
        "G1",
        "eval-gate",
        10,
        1.0,
        "none",
        "none",
    )


def test_a_missed_mutation_fails(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes: list[Outcome] = ["blocked"] * 8 + ["missed", "stale"]
    monkeypatch.setattr(mutations_cli, "run_mutations", _fake(outcomes))
    assert main(["eval", "mutations"]) == 1
    out = capsys.readouterr().out
    assert "blocked 8/10" in out and "m8 missed" in out and "m9 stale" in out
