"""The demo page: eval tables from runs.csv and the sample answers, all escaped, no scripts."""

from demo_kit import KEY, scenario, search, transcript
from report_kit import run

from sec_agent.demo.page import render_page
from sec_agent.demo.samples import Sample, pick_samples
from sec_agent.runs import RunRow


def _rows() -> list[RunRow]:
    return [
        run("N1", "b0", 0.5, n=300, ci=(0.4, 0.6)),
        run("N1", "b2", 0.9, n=300, ci=(0.85, 0.94)),
        run("A1", "agent", 0.7, n=50, ci=(0.56, 0.81)),
        run("S1_attack_block", "guarded", 0.97, n=100, ci=(0.91, 0.99), split="none"),
        run("J1_kappa", "grader", 0.8, unit="kappa", n=38),
        run("R1_ndcg@10", "hybrid", 0.6, n=89, ci=(0.53, 0.67)),
        run("L1_rerank_p50", "minilm", 12.0, unit="ms", n=200),
    ]


def _samples() -> list[Sample]:
    text = f"Costs <b>rise</b> [{KEY}]."
    ev = search([{"citation": KEY, "text": "passage & <script>x</script>"}])
    return pick_samples([scenario("a1-001", question="Q <i>?")], [transcript("a1-001", text, [ev])])


def test_page_shows_each_family_with_n_and_interval() -> None:
    page = render_page(_rows(), _samples())
    for shown in ("N1", "b0", "b2", "A1", "S1_attack_block", "J1_kappa", "R1_ndcg@10"):
        assert shown in page
    assert "90.0%" in page
    assert "85.0% to 94.0%" in page
    assert ">300<" in page
    assert "L1_rerank_p50" not in page


def test_page_states_model_and_simulated_safety_items() -> None:
    page = render_page(_rows(), _samples())
    assert "local Qwen" in page
    assert "thinking off" in page
    assert "simulated" in page.lower()
    assert "not investment advice" in page.lower()


def test_page_escapes_transcript_text_and_has_no_scripts_or_network() -> None:
    page = render_page(_rows(), _samples())
    assert "<script" not in page
    assert "&lt;script&gt;" in page
    assert "Costs &lt;b&gt;rise&lt;/b&gt;" in page
    assert "Q &lt;i&gt;?" in page
    assert "passage &amp; " in page
    assert "fetch(" not in page
    assert "http://" not in page


def test_page_is_deterministic() -> None:
    assert render_page(_rows(), _samples()) == render_page(_rows(), _samples())


def test_page_title_and_heading_use_the_display_name() -> None:
    page = render_page(_rows(), _samples())
    assert "<title>Verified SEC Filings Agent</title>" in page
    assert "<h1>Verified SEC Filings Agent</h1>" in page
    assert "Research Agent" not in page
