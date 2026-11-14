"""Apply one mutation to a throwaway copy of the package and run the gate against it.

The copy is put first on `PYTHONPATH`, so the gate imports the mutated code while it reads
the committed results and baseline from the repository. The source tree is never touched.
A mutation whose snippet is not in the source exactly once is `stale`: it is reported, never
run, so a refactor cannot turn a mutation into a silent pass.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.gate.mutations import Mutation

Outcome = Literal["blocked", "missed", "crashed", "stale"]
GateRun = Callable[[Path], tuple[int, str]]
"""Directory that holds the mutated `sec_agent` -> (gate exit code, first finding)."""


class StaleMutationError(ValueError):
    pass


class MutationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    outcome: Outcome
    detail: str


def apply_mutation(package: Path, mutation: Mutation) -> None:
    path = package / mutation.path
    text = path.read_text("utf-8")
    if (count := text.count(mutation.old)) != 1:
        raise StaleMutationError(f"{mutation.path}: snippet found {count} times, not once")
    path.write_text(text.replace(mutation.old, mutation.new), "utf-8", newline="")


def run_mutations(
    mutations: Sequence[Mutation], package: Path, gate: GateRun, *, workers: int
) -> list[MutationResult]:
    """`package`: the `sec_agent` directory to copy. Results in the order of `mutations`."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, m, package, gate) for m in mutations]
        return [f.result() for f in futures]


def _one(mutation: Mutation, package: Path, gate: GateRun) -> MutationResult:
    with tempfile.TemporaryDirectory(prefix=f"mut-{mutation.id}-") as tmp:
        copy = Path(tmp) / package.name
        shutil.copytree(package, copy, ignore=shutil.ignore_patterns("__pycache__"))
        try:
            apply_mutation(copy, mutation)
        except StaleMutationError as error:
            return MutationResult(id=mutation.id, outcome="stale", detail=str(error))
        code, detail = gate(Path(tmp))
    outcome: Outcome = "blocked" if code == 1 else "missed" if code == 0 else "crashed"
    return MutationResult(id=mutation.id, outcome=outcome, detail=detail)


def subprocess_gate(repo: Path, baseline: Path) -> GateRun:
    """Run `sec-agent eval gate` in a fresh interpreter with the mutated copy first."""

    def run(src: Path) -> tuple[int, str]:
        env = {**os.environ, "PYTHONPATH": str(src)}
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        code = "import sys; from sec_agent.cli import main; sys.exit(main(sys.argv[1:]))"
        done = subprocess.run(
            [sys.executable, "-c", code, "eval", "gate", "--baseline", str(baseline)],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        lines = [ln.strip() for ln in (done.stdout + done.stderr).splitlines() if ln.strip()]
        first = next((ln for ln in lines if not ln.startswith("gate")), lines[-1] if lines else "")
        return done.returncode, first

    return run
