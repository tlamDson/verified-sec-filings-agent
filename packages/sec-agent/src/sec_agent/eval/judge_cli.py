"""`sec-agent eval judge sample|score`: the G-judge sample and J1 (no model, no database).

`sample` reads the committed eval answers (G-num test answers, A1 transcripts), takes a
stratified seeded sample and writes `items.jsonl` (blind: what raters and judges see)
and `key.jsonl` (hidden: origin, stratum, code verdict). `score` reads the labels and
each judge's verdict file, prints kappa, TPR and TNR per judge (the code grader always
included), and with `--record` appends the J1 rows to runs.csv.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.eval.agent.scenarios import Transcript, read_scenarios
from sec_agent.eval.judge.models import STRATA, KeyEntry, Label, Verdict
from sec_agent.eval.judge.pool import agent_candidates, numeric_candidates
from sec_agent.eval.judge.rows import judge_rows
from sec_agent.eval.judge.sample import sample_items
from sec_agent.eval.judge.score import GRADER, JudgeScore, grader_verdicts, score_judge
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.jsonl import read_jsonl, write_jsonl

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_DIR = Path("results/judge/v1")
DEFAULT_TOTAL = 100
DEFAULT_SEED = 20261114
SPLIT = "test"


def add_commands(subparsers: "Subparsers") -> None:
    judge = subparsers.add_parser("judge", help="G-judge sample and J1 judge calibration")
    actions = judge.add_subparsers(dest="judge_command", metavar="action", required=True)

    sample = actions.add_parser("sample", help="write blind items and their key")
    sample.add_argument("--questions", type=Path, default=Path("data/golden/g_num.jsonl"))
    sample.add_argument("--numeric-dir", type=Path, default=Path("results/numeric/test"))
    sample.add_argument("--numeric-systems", default="b0,b1,b2")
    sample.add_argument("--scenarios", type=Path, default=Path("data/golden/agent_scenarios.jsonl"))
    sample.add_argument("--agent-dir", type=Path, default=Path("results/agent/test"))
    sample.add_argument("--agent-systems", default="agent,rag")
    sample.add_argument("--total", type=int, default=DEFAULT_TOTAL)
    sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sample.add_argument("--out", type=Path, default=DEFAULT_DIR)
    sample.set_defaults(run=_sample)

    score = actions.add_parser("score", help="J1: kappa, TPR, TNR of each judge")
    score.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="holds key.jsonl")
    score.add_argument("--labels", type=Path, required=True)
    score.add_argument(
        "--labelled-by", default=None, help="who made the labels (default: their rater fields)"
    )
    score.add_argument("--verdicts", default="", help="comma-separated verdict files")
    add_record_options(score)
    score.set_defaults(run=_score)


def _names(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def _sample(args: argparse.Namespace) -> int:
    numeric = {s: args.numeric_dir / f"{s}.jsonl" for s in _names(args.numeric_systems)}
    agent = {s: args.agent_dir / f"{s}.jsonl" for s in _names(args.agent_systems)}
    if missing := [str(p) for p in [*numeric.values(), *agent.values()] if not p.exists()]:
        print(f"error: no answers file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        questions = [q for q in read_jsonl(args.questions, NumQuestion) if q.split == SPLIT]
        scenarios = [s for s in read_scenarios(args.scenarios) if s.split == SPLIT]
        pool = [c for p in numeric.values() for c in numeric_candidates(questions, _answers(p))]
        pool += [c for p in agent.values() for c in agent_candidates(scenarios, _transcripts(p))]
        items, key = sample_items(pool, total=args.total, seed=args.seed)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    write_jsonl(args.out / "items.jsonl", items)
    write_jsonl(args.out / "key.jsonl", key)
    available = Counter(c.stratum for c in pool)
    taken = Counter(k.stratum for k in key)
    rows = [["stratum", "pool", "sampled"]]
    rows += [[s, str(available[s]), str(taken[s])] for s in STRATA]
    print("\n".join(table(rows)))
    print(f"{len(items)} items in {args.out} (seed {args.seed}); give raters items.jsonl only")
    return 0


def _answers(path: Path) -> list[AnswerRecord]:
    return read_jsonl(path, AnswerRecord)


def _transcripts(path: Path) -> list[Transcript]:
    return read_jsonl(path, Transcript)


def _score(args: argparse.Namespace) -> int:
    if not args.labels.exists():
        print(f"error: no labels file: {args.labels}", file=sys.stderr)
        return 2
    try:
        key = read_jsonl(args.dir / "key.jsonl", KeyEntry)
        labels = read_jsonl(args.labels, Label)
        if unknown := sorted({lb.id for lb in labels} - {k.id for k in key}):
            raise ValueError(f"labels for items not in the key: {', '.join(unknown[:5])}")
        scores = [score_judge(labels, grader_verdicts(key), judge=GRADER)]
        for path in [Path(p) for p in _names(args.verdicts)]:
            verdicts = read_jsonl(path, Verdict)
            if not verdicts:
                raise ValueError(f"no verdicts in {path}")
            scores.append(score_judge(labels, verdicts, judge=verdicts[0].judge))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    labelled_by: str = args.labelled_by or "; ".join(sorted({lb.rater for lb in labels}))
    _print(scores, labelled_by)
    return record_rows(
        args,
        lambda date, sha: judge_rows(scores, labelled_by=labelled_by, date=date, git_sha=sha),
    )


def _print(scores: list[JudgeScore], labelled_by: str) -> None:
    print(f"J1 against blind labels ({labelled_by})")
    rows = [["judge", "n", "kappa", "TPR", "TNR", "unsure", "missing"]]
    rows += [
        [
            s.judge,
            str(s.n),
            _num(s.kappa),
            _num(s.tpr),
            _num(s.tnr),
            str(s.unsure),
            str(s.missing),
        ]
        for s in scores
    ]
    print("\n".join(table(rows)))


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"
