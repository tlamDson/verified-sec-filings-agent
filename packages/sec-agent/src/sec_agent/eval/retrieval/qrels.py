"""Read TREC qrels (`qid 0 docid grade`), as `sec-agent golden qrels` writes them."""

from typing import cast

from sec_agent.golden.gret.models import Grade

Qrels = dict[str, dict[str, Grade]]
"""qid -> docid -> grade. A chunk not listed was not pooled and counts as not relevant."""


def parse_qrels(text: str) -> Qrels:
    qrels: Qrels = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4 or fields[3] not in ("0", "1", "2"):
            raise ValueError(f"qrels line {number}: want `qid 0 docid grade` with grade 0-2")
        qid, _, docid, grade = fields
        judged = qrels.setdefault(qid, {})
        if docid in judged:
            raise ValueError(f"qrels line {number}: {qid} {docid} is judged twice")
        judged[docid] = cast(Grade, int(grade))
    return qrels
