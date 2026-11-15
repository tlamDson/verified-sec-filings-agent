"""`sec-agent demo build` writes the static site from committed files only."""

from pathlib import Path

from demo_kit import KEY, scenario, search, transcript
from report_kit import run

from sec_agent.cli import main
from sec_agent.runs import append_run

ROOT = Path(__file__).resolve().parents[4]


def _inputs(tmp: Path) -> list[str]:
    runs = tmp / "runs.csv"
    append_run(runs, run("A1", "agent", 0.7, n=50, ci=(0.56, 0.81)))
    scenarios = tmp / "scenarios.jsonl"
    scenarios.write_text(scenario("a1-001").model_dump_json() + "\n", "utf-8")
    ev = search([{"citation": KEY, "text": "costs could rise"}])
    transcripts = tmp / "agent.jsonl"
    line = transcript("a1-001", f"x [{KEY}]", [ev]).model_dump_json() + "\n"
    transcripts.write_text(line, "utf-8")
    return ["--runs", str(runs), "--scenarios", str(scenarios), "--transcripts", str(transcripts)]


def test_build_writes_index_and_nojekyll(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert main(["demo", "build", *_inputs(tmp_path), "--out", str(out)]) == 0
    page = (out / "index.html").read_text("utf-8")
    assert "costs could rise" in page
    assert "70.0%" in page
    assert (out / ".nojekyll").exists()


def test_build_reports_a_missing_input(tmp_path: Path) -> None:
    args = _inputs(tmp_path)
    args[args.index("--transcripts") + 1] = str(tmp_path / "missing.jsonl")
    assert main(["demo", "build", *args, "--out", str(tmp_path / "site")]) == 2


def test_build_over_committed_results_has_five_to_ten_samples(tmp_path: Path) -> None:
    out = tmp_path / "site"
    args = [
        "--runs",
        str(ROOT / "runs.csv"),
        "--scenarios",
        str(ROOT / "data" / "golden" / "agent_scenarios.jsonl"),
        "--transcripts",
        str(ROOT / "results" / "agent" / "test" / "agent.jsonl"),
    ]
    assert main(["demo", "build", *args, "--out", str(out)]) == 0
    page = (out / "index.html").read_text("utf-8")
    assert 5 <= page.count('<article class="sample"') <= 10
    articles = page.split('<article class="sample"')[1:]
    with_passages = [a for a in articles if '<li class="passage"' in a]
    assert len(with_passages) >= 5
