"""`sec-agent golden split`: write the seeded company split."""

from pathlib import Path

import pytest

from sec_agent.cli import main
from sec_agent.golden.split import SPLIT_SEED, build_split, read_split
from sec_agent.golden.universe import load_universe


def test_split_writes_the_seeded_split(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "split.json"
    assert main(["golden", "split", "--out", str(out)]) == 0
    assert read_split(out) == build_split(load_universe(), seed=SPLIT_SEED)
    assert "train 30, dev 10, test 10" in capsys.readouterr().out


def test_split_takes_another_seed(tmp_path: Path) -> None:
    out = tmp_path / "split.json"
    assert main(["golden", "split", "--seed", "99", "--out", str(out)]) == 0
    assert read_split(out).seed == 99
