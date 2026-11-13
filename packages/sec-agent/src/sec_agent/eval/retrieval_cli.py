"""`sec-agent eval retrieval run|score`: R1 baseline runs from a snapshot, and their scores.

`run` pins one retrieval snapshot, verifies it before and after, and writes one TREC run
per system plus the snapshot manifest; the runs feed both pooling (`golden pool`) and
scoring. `score` reads runs and qrels from files only.
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg

from sec_agent.edgar.urls import normalize_cik
from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.eval.records import retrieval_rows
from sec_agent.eval.retrieval.metrics import METRICS
from sec_agent.eval.retrieval.qrels import parse_qrels
from sec_agent.eval.retrieval.rankers import RANDOM_SEED, Ranker, collect_runs
from sec_agent.eval.retrieval.report import RetrievalReport, retrieval_report
from sec_agent.eval.stats.bootstrap import DEFAULT_RESAMPLES, BootstrapResult
from sec_agent.golden.gret.cli import DEFAULT_QRELS, DEFAULT_QUESTIONS
from sec_agent.golden.gret.models import RunHit
from sec_agent.golden.gret.questions import load_questions
from sec_agent.golden.gret.trec import parse_run, run_text
from sec_agent.golden.split import DEFAULT_SPLIT_FILE, read_split
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.errors import RetrievalError
from sec_agent.retrieval.models import EmbedderSpec, SearchMode
from sec_agent.retrieval.snapshot import load_snapshot, verify_snapshot, write_manifest

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_OUT = Path("results/retrieval")
BOOTSTRAP_SEED = 20261117
SEARCH_SYSTEMS: dict[str, SearchMode] = {"bm25": "lexical", "vector": "dense", "hybrid": "hybrid"}
SYSTEMS = ("random", *SEARCH_SYSTEMS)


def add_commands(actions: "Subparsers") -> None:
    retrieval = actions.add_parser("retrieval", help="R1: retrieval runs and their scores")
    steps = retrieval.add_subparsers(dest="retrieval_command", metavar="step", required=True)

    run = steps.add_parser("run", help="write a TREC run per baseline from a snapshot")
    add_database_url_option(run)
    run.add_argument("--snapshot", required=True, help="retrieval snapshot to pin")
    _add_question_options(run)
    run.add_argument("--systems", default=",".join(SYSTEMS), help=f"of {', '.join(SYSTEMS)}")
    run.add_argument("--depth", type=int, default=100, help="chunks per question (100)")
    run.add_argument("--candidates", type=int, default=50, help="per arm, hybrid (50)")
    run.add_argument("--seed", type=int, default=RANDOM_SEED, help="random baseline seed")
    run.add_argument("--device", default=None, help="torch device for the query embedder")
    run.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    run.set_defaults(run=_run)

    score = steps.add_parser("score", help="recall@5, nDCG@10, MRR@10 with company bootstrap")
    score.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    _add_question_options(score)
    score.add_argument("--run", dest="runs", type=Path, action="append", required=True)
    score.add_argument("--baseline", default=None, help="system to compare every other with")
    score.add_argument("--oracle", action="store_true", help="add the qrels-ordered ceiling")
    score.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    score.add_argument("--seed", type=int, default=BOOTSTRAP_SEED, help="bootstrap seed")
    score.add_argument("--index-version", default="", help="for runs.csv rows")
    add_record_options(score)
    score.set_defaults(run=_score)


def _add_question_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--split-file", type=Path, default=DEFAULT_SPLIT_FILE)


def query_embedder(spec: EmbedderSpec, device: str | None) -> Embedder:
    from sec_agent.retrieval.sentence_transformer import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(spec, device=device)


def _run(args: argparse.Namespace) -> int:
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    if unknown := sorted(set(systems) - set(SYSTEMS)):
        print(f"error: unknown systems {unknown}; choose from {list(SYSTEMS)}", file=sys.stderr)
        return 2
    if (url := database_url_or_error(args)) is None:
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            snapshot = load_snapshot(conn, args.snapshot)
            verify_snapshot(conn, snapshot)
            split = read_split(args.split_file)
            questions = load_questions(args.questions, split)
            rankers = _rankers(conn, args, systems, snapshot.spec, snapshot.index_version)
            cik_of = {c.ticker: normalize_cik(c.cik) for c in split.companies}
            hits = collect_runs(questions, rankers, cik_of, args.depth)
            verify_snapshot(conn, snapshot)
        except (RetrievalError, ValueError, OSError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for system in systems:
        text = run_text(h for h in hits if h.system == system)
        (out / f"{system}.run").write_text(text, "utf-8", newline="\n")
    write_manifest(snapshot, out / "snapshot.json")
    print(f"snapshot {snapshot.name} verified before and after ({snapshot.index_version})")
    print(f"wrote {len(systems)} runs for {len(questions)} questions to {out}")
    return 0


def _rankers(
    conn: psycopg.Connection[Any],
    args: argparse.Namespace,
    systems: list[str],
    spec: EmbedderSpec,
    index_version: str,
) -> dict[str, Ranker]:
    from sec_agent.eval.retrieval.postgres import CompanyChunks, random_ranker, search_ranker
    from sec_agent.retrieval.space import make_space

    space = make_space(index_version, spec)
    needs_vectors = any(SEARCH_SYSTEMS.get(s, "lexical") != "lexical" for s in systems)
    embedder = query_embedder(spec, args.device) if needs_vectors else None
    rankers: dict[str, Ranker] = {}
    for system in systems:
        if system == "random":
            rankers[system] = random_ranker(CompanyChunks(conn, index_version), seed=args.seed)
        else:
            mode = SEARCH_SYSTEMS[system]
            rankers[system] = search_ranker(conn, space, embedder, mode, candidates=args.candidates)
    return rankers


def _score(args: argparse.Namespace) -> int:
    try:
        questions = load_questions(args.questions, read_split(args.split_file))
        qrels = parse_qrels(Path(args.qrels).read_text("utf-8"))
        hits: list[RunHit] = []
        for path in args.runs:
            try:
                hits += parse_run(Path(path).read_text("utf-8"))
            except ValueError as error:
                raise ValueError(f"{Path(path).name}: {error}") from error
        report = retrieval_report(
            questions,
            qrels,
            hits,
            baseline=args.baseline,
            resamples=args.resamples,
            seed=args.seed,
            oracle=args.oracle,
        )
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    _print(report)
    return record_rows(
        args,
        lambda date, sha: retrieval_rows(
            report, date=date, git_sha=sha, index_version=args.index_version
        ),
    )


def _cell(r: BootstrapResult, signed: bool = False) -> str:
    estimate = f"{r.estimate:+.3f}" if signed else f"{r.estimate:.3f}"
    return f"{estimate} [{r.low:.3f}, {r.high:.3f}]"


def _print(report: RetrievalReport) -> None:
    print(
        f"R1 retrieval: {report.scored} of {report.questions} questions scored,"
        f" {report.companies} companies; 95% intervals from a bootstrap over companies"
        f" ({report.resamples} resamples)"
    )
    if report.unscored:
        print(f"no relevant chunk judged, not scored: {', '.join(report.unscored)}")
    header = ["system", *METRICS]
    rows = [[s.system, *(_cell(s.metrics[m]) for m in METRICS)] for s in report.systems]
    for line in table([header, *rows]):
        print(f"  {line}")
    if report.comparisons:
        print("paired differences (bootstrap over companies):")
        rows = [
            [
                f"{c.system} - {c.baseline}",
                c.metric,
                _cell(c.result, signed=True),
                f"p = {c.result.p_value:.4f}",
            ]
            for c in report.comparisons
        ]
        for line in table(rows):
            print(f"  {line}")
