"""Mutations are applied to a copy of the package, never to the source tree."""

from pathlib import Path

import pytest

import sec_agent
from sec_agent.eval.gate.mutate import StaleMutationError, apply_mutation, run_mutations
from sec_agent.eval.gate.mutations import MUTATIONS, Mutation

PACKAGE = Path(sec_agent.__file__).parent
M = Mutation(id="m1", path="mod.py", old="return 1", new="return 2", why="w")
SOURCE = "def f():\n    return 1\n"


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg" / "sec_agent"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text(SOURCE, "utf-8")
    return pkg


def test_ten_mutations_with_unique_ids() -> None:
    assert len(MUTATIONS) == 10
    assert len({m.id for m in MUTATIONS}) == 10


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.id)
def test_every_mutation_still_matches_the_source_once(mutation: Mutation) -> None:
    text = (PACKAGE / mutation.path).read_text("utf-8")
    assert text.count(mutation.old) == 1
    assert mutation.old != mutation.new


def test_apply_replaces_once(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    apply_mutation(pkg, M)
    assert "return 2" in (pkg / "mod.py").read_text("utf-8")


def test_apply_refuses_a_stale_or_ambiguous_snippet(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    with pytest.raises(StaleMutationError):
        apply_mutation(pkg, M.model_copy(update={"old": "return 3"}))
    (pkg / "mod.py").write_text("return 1\nreturn 1\n", "utf-8")
    with pytest.raises(StaleMutationError):
        apply_mutation(pkg, M)


def test_run_classifies_by_gate_exit_and_leaves_source_alone(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    seen: list[str] = []

    def gate(src: Path) -> tuple[int, str]:
        line = (src / "sec_agent" / "mod.py").read_text("utf-8").split("\n")[1].strip()
        seen.append(line)
        return {"return 2": 1, "return 3": 0}.get(line, 2), "drift N1:b2"

    mutations = [
        M,
        M.model_copy(update={"id": "m2", "new": "return 3"}),
        M.model_copy(update={"id": "m3", "new": "return 4"}),
        M.model_copy(update={"id": "m4", "old": "nope"}),
    ]
    results = run_mutations(mutations, pkg, gate, workers=2)
    assert [(r.id, r.outcome) for r in results] == [
        ("m1", "blocked"),
        ("m2", "missed"),
        ("m3", "crashed"),
        ("m4", "stale"),
    ]
    assert results[0].detail == "drift N1:b2"
    assert (pkg / "mod.py").read_text("utf-8") == SOURCE
    assert sorted(seen) == ["return 2", "return 3", "return 4"]
