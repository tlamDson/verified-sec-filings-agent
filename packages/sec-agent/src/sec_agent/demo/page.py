"""The demo page as one static HTML string: no script, no request at view time.

Every number on the page is a runs.csv row (shown the way the README shows it) or text of a
committed transcript; all transcript text is escaped.
"""

from collections.abc import Sequence
from html import escape

from sec_agent.demo.samples import Sample
from sec_agent.report.format import show_interval, show_value
from sec_agent.report.latest import latest_rows
from sec_agent.report.render import family_of
from sec_agent.runs import RunRow

REPO_URL = "https://github.com/tlamDson/verified-sec-filings-agent"

# family -> (title, caveat). Caveats hold no numbers: those come from the rows.
SHOWN: dict[str, tuple[str, str]] = {
    "N1": (
        "Numeric answers (N1)",
        "Numeric questions on the test companies; the answer must match the XBRL value. "
        "b0 and b1 are baselines on the same local model, b2 is the agent. "
        "p rows are exact two-sided McNemar tests between two systems.",
    ),
    "A1": (
        "Agent scenarios (A1)",
        "A scenario passes when every check passes: tool and resolved arguments, traced "
        "figure, citation, faithfulness and text.",
    ),
    "R1": (
        "Retrieval (R1)",
        "Questions on the test companies; intervals resample companies. diff rows compare "
        "two systems on the same questions and p rows are their paired tests.",
    ),
    "S1": (
        "Safety (S1, simulated items)",
        "The safety set is synthetic: its attack items and filing passages are simulated, "
        "so these rows say nothing about real attackers or real users.",
    ),
    "J1": (
        "Grader agreement (J1)",
        "Agreement of the graders with labels from LLM raters, not human annotators; items "
        "marked unsure are excluded.",
    ),
}

_CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#5d5d58;--line:#deddd8;--card:#fff;--accent:#1f5fa8}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe7;--muted:#a6a59f;
--line:#34332f;--card:#1f1f1d;--accent:#7fb2ee}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}
h1{font-size:1.7rem;margin:0 0 8px}
h2{margin-top:40px;border-bottom:1px solid var(--line);padding-bottom:4px}
h3{margin:28px 0 4px}
.muted,.caveat{color:var(--muted)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:4px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.sample{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:12px 16px;margin:16px 0}
.answer{white-space:pre-wrap;overflow-wrap:anywhere}
.passage{margin:8px 0}
.passage blockquote{white-space:pre-wrap;margin:4px 0 0;padding-left:12px;
border-left:3px solid var(--line);color:var(--muted);overflow-wrap:anywhere}
code{font-size:.85em;overflow-wrap:anywhere}
"""


def _cell(text: str, numeric: bool = False) -> str:
    return f'<td class="num">{escape(text)}</td>' if numeric else f"<td>{escape(text)}</td>"


def _table(rows: Sequence[RunRow]) -> str:
    head = "".join(f"<th>{h}</th>" for h in ("Metric", "System", "Split", "Cohort", "n"))
    head += "<th>Value</th><th>95% interval</th>"
    body = "".join(
        "<tr>"
        + _cell(row.metric)
        + _cell(row.system)
        + _cell(row.split)
        + _cell(row.cohort)
        + _cell(str(row.n), numeric=True)
        + _cell(show_value(row), numeric=True)
        + _cell(show_interval(row))
        + "</tr>"
        for row in rows
    )
    return f'<div class="scroll"><table><tr>{head}</tr>{body}</table></div>'


def _results(rows: Sequence[RunRow]) -> str:
    by_family: dict[str, list[RunRow]] = {}
    for row in latest_rows(rows):
        by_family.setdefault(family_of(row.metric), []).append(row)
    parts: list[str] = []
    for family, (title, caveat) in SHOWN.items():
        parts.append(f'<h3>{escape(title)}</h3><p class="caveat">{escape(caveat)}</p>')
        if family in by_family:
            parts.append(_table(by_family[family]))
        else:
            parts.append("<p>No row in runs.csv yet; nothing is claimed.</p>")
    return "".join(parts)


def _sample(sample: Sample) -> str:
    out = [f'<article class="sample" id="{escape(sample.scenario_id)}">']
    out.append(f'<p class="muted">{escape(sample.scenario_id)} · {escape(sample.category)}</p>')
    for turn in sample.earlier_turns:
        out.append(f'<p class="muted"><strong>Earlier:</strong> {escape(turn)}</p>')
    out.append(f"<p><strong>Question:</strong> {escape(sample.question)}</p>")
    out.append(f'<div class="answer">{escape(sample.answer)}</div>')
    if sample.passages:
        out.append("<h4>Cited passages</h4><ul>")
        for passage in sample.passages:
            out.append(
                f'<li class="passage"><code>[{escape(passage.citation)}]</code>'
                f"<blockquote>{escape(passage.text)}</blockquote></li>"
            )
        out.append("</ul>")
    if sample.tools:
        out.append("<h4>Tool calls behind the figures</h4><ul>")
        for tool in sample.tools:
            links = "".join(f' <a href="{escape(url)}">filing</a>' for url in tool.filing_urls)
            out.append(
                f"<li><code>{escape(tool.name)}({escape(tool.arguments)})</code>{links}</li>"
            )
        out.append("</ul>")
    out.append("</article>")
    return "".join(out)


def render_page(rows: Sequence[RunRow], samples: Sequence[Sample]) -> str:
    return "".join(
        [
            '<!doctype html><html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            "<title>Verified SEC Filings Agent</title>",
            f"<style>{_CSS}</style></head><body><main>",
            "<h1>Verified SEC Filings Agent</h1>",
            "<p>A research agent over public SEC filings where every number comes from a "
            "deterministic tool (XBRL lookup, ratio code) or a cited filing passage. This "
            "page is static: it shows committed results and makes no model or API call.</p>",
            "<p>All answers and model-graded results came from the local Qwen model "
            "(llama.cpp, thinking off), at no cost: no paid API. Safety (S1) items are "
            "simulated.</p>",
            "<p><strong>Not investment advice.</strong> The agent refuses advice and shows "
            "historical figures from filings only.</p>",
            f'<p><a href="{REPO_URL}">Source, design and runs.csv</a></p>',
            "<h2>Eval results</h2>",
            '<p class="muted">Every number is a row of runs.csv (the latest row for each '
            "metric, system, split and cohort).</p>",
            _results(rows),
            "<h2>Sample answers</h2>",
            '<p class="muted">Answers of the agent on test scenarios, copied from the '
            "committed transcripts with the passages they cite and the tool calls behind "
            "their figures.</p>",
            *(_sample(s) for s in samples),
            "</main></body></html>\n",
        ]
    )
