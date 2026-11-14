"""`sec-agent eval safety score`: rates from record files, appended to runs.csv on request;
and `golden gred`, which writes the set. Records are simulated (made up for the test)."""

from pathlib import Path

import pytest

from sec_agent.cli import main
from sec_agent.eval.safety.records import SafetyRecord
from sec_agent.golden.gred.generate import generate_gred
from sec_agent.golden.gred.models import RedItem, RedKind
from sec_agent.golden.jsonl import read_jsonl, write_jsonl
from sec_agent.runs import read_runs


def record(item_id: str, kind: RedKind, succeeded: bool | None, system: str) -> SafetyRecord:
    return SafetyRecord(
        item_id=item_id,
        kind=kind,
        system=system,
        status="answered",
        reason=None,
        text="SIMULATED",
        attack_succeeded=succeeded,
        exposed=True,
        refused=False,
        llm_calls=1,
    )


def test_score_prints_rates_and_records_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for system in ("guarded", "none"):
        write_jsonl(
            tmp_path / f"{system}.jsonl",
            [
                record("d", "direct", system == "none", system),
                record("i", "indirect", system == "none", system),
                record("b", "benign", None, system),
            ],
        )
    runs = tmp_path / "runs.csv"
    code = main(
        [
            "eval", "safety", "score", "--results-dir", str(tmp_path), "--record", str(runs),
            "--git-sha", "abc1234", "--config", "model=sim", "--notes", "simulated records",
        ]
    )  # fmt: skip
    assert code == 0
    out = capsys.readouterr().out
    assert "guarded" in out
    assert "2/2 1.000" in out
    rows = read_runs(runs)
    assert {(r.metric, r.system) for r in rows} >= {
        ("S1_attack_block", "guarded"),
        ("S1_indirect_success", "none"),
        ("S1_false_refusal", "guarded"),
    }
    assert all(r.config == "model=sim" for r in rows)


def test_score_needs_every_records_file(tmp_path: Path) -> None:
    assert main(["eval", "safety", "score", "--results-dir", str(tmp_path)]) == 2


def test_golden_gred_writes_the_set(tmp_path: Path) -> None:
    out = tmp_path / "g_red.jsonl"
    assert main(["golden", "gred", "--out", str(out)]) == 0
    assert read_jsonl(out, RedItem) == generate_gred()
