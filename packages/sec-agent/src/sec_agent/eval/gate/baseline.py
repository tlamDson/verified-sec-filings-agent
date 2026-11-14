"""The committed baseline file (`results/gate/baseline.json`)."""

from pathlib import Path

from sec_agent.eval.gate.models import GateSnapshot

DEFAULT_BASELINE = Path("results/gate/baseline.json")


def read_baseline(path: Path) -> GateSnapshot:
    return GateSnapshot.model_validate_json(path.read_text("utf-8"))


def write_baseline(path: Path, snapshot: GateSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json(indent=2) + "\n", "utf-8", newline="\n")
