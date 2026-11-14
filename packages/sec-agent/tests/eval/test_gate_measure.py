"""The gate over the committed results: it passes as committed, and the CLI reports it."""

from pathlib import Path

import pytest

from sec_agent.cli import main
from sec_agent.eval.gate.baseline import read_baseline
from sec_agent.eval.gate.compare import compare
from sec_agent.eval.gate.measure import FAMILIES, measure

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "results" / "gate" / "baseline.json"


@pytest.fixture(scope="module")
def measured():  # noqa: ANN201
    return measure(REPO)


def test_committed_results_match_the_committed_baseline(measured) -> None:  # noqa: ANN001
    assert compare(read_baseline(BASELINE), measured) == []


def test_baseline_covers_every_family(measured) -> None:  # noqa: ANN001
    families = {m.family for m in read_baseline(BASELINE).metrics}
    assert families == set(FAMILIES) == set(measured.inputs) == {"N1", "A1", "R1", "S1", "J1"}


def test_gate_cli_passes_and_update_writes_the_same_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO)
    assert main(["eval", "gate"]) == 0
    assert "gate passed" in capsys.readouterr().out
    out = tmp_path / "baseline.json"
    assert main(["eval", "gate", "--baseline", str(out), "--update"]) == 0
    assert read_baseline(out) == read_baseline(BASELINE)


def test_gate_cli_fails_on_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO)
    base = read_baseline(BASELINE)
    metrics = tuple(
        m.model_copy(update={"value": m.value + 0.1}) if m.name == "N1:b2" else m
        for m in base.metrics
    )
    path = tmp_path / "baseline.json"
    path.write_text(base.model_copy(update={"metrics": metrics}).model_dump_json(), "utf-8")
    assert main(["eval", "gate", "--baseline", str(path)]) == 1
    assert "drift N1:b2" in capsys.readouterr().out


def test_gate_cli_refuses_a_missing_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO)
    assert main(["eval", "gate", "--baseline", str(tmp_path / "none.json")]) == 2
