"""`sec-agent chaos fake-llm|integrity|kill-worker|load-rows`."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg

from sec_agent.chaos.fake_llm import DEFAULT_TOOL_ARGUMENTS, FakeLLMState, create_fake_llm
from sec_agent.chaos.integrity import check_ingest
from sec_agent.chaos.k6_summary import load_rows, parse_k6_summary
from sec_agent.chaos.rows import kill_rows
from sec_agent.chaos.worker_kill import (
    ChaosError,
    KillPlan,
    PostgresQueueProbe,
    kill_worker_mid_job,
)
from sec_agent.eval.output import add_record_options, record_rows
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.xbrl.ingest import KIND

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

_RUN_CLI = "import sys; from sec_agent.cli import main; sys.exit(main(sys.argv[1:]))"


def add_commands(subparsers: "Subparsers") -> None:
    chaos = subparsers.add_parser("chaos", help="load and chaos tooling (simulated traffic)")
    actions = chaos.add_subparsers(dest="chaos_command", metavar="action", required=True)

    fake = actions.add_parser("fake-llm", help="serve a simulated OpenAI-compatible model")
    fake.add_argument("--host", default="127.0.0.1", help="address to listen on (127.0.0.1)")
    fake.add_argument("--port", type=int, default=8081, help="port to listen on (8081)")
    fake.add_argument("--mode", choices=("ok", "rate_limited"), default="ok")
    fake.add_argument(
        "--tool-arguments",
        default=json.dumps(DEFAULT_TOOL_ARGUMENTS),
        help="JSON arguments of the get_fact call the model asks for",
    )
    fake.set_defaults(run=_fake_llm)

    integrity = actions.add_parser("integrity", help="duplicates and open jobs of an ingest")
    add_database_url_option(integrity)
    integrity.add_argument("--index-version", required=True, help="snapshot to check, e.g. v1")
    integrity.set_defaults(run=_integrity)

    kill = actions.add_parser(
        "kill-worker", help="run sec-agent workers on a queued ingest and kill one mid-job"
    )
    add_database_url_option(kill)
    kill.add_argument("--index-version", required=True, help="snapshot being ingested")
    kill.add_argument("--workers", type=int, default=3, help="worker processes (3)")
    kill.add_argument("--lease", type=float, default=10.0, help="worker lease seconds (10)")
    kill.add_argument("--heartbeat", type=float, default=3.0, help="heartbeat seconds (3)")
    kill.add_argument("--timeout", type=float, default=900.0, help="give up after (900 s)")
    add_record_options(kill)
    kill.set_defaults(run=_kill_worker)

    rows = actions.add_parser("load-rows", help="k6 summary export -> runs.csv rows")
    rows.add_argument("summary", type=Path, help="k6 --summary-export JSON")
    rows.add_argument("--system", required=True, help="what was loaded, e.g. api-x3+fake-llm")
    rows.add_argument("--config", default="", help="scenario, e.g. '200 VU, kill api-2'")
    add_record_options(rows)
    rows.set_defaults(run=_load_rows)


def _fake_llm(args: argparse.Namespace) -> int:
    import uvicorn

    try:
        arguments: object = json.loads(args.tool_arguments)
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        print("error: --tool-arguments must be a JSON object", file=sys.stderr)
        return 2
    state = FakeLLMState(mode=args.mode, tool_arguments=dict(arguments))  # pyright: ignore[reportUnknownArgumentType]
    uvicorn.run(create_fake_llm(state), host=args.host, port=args.port)
    return 0


def _integrity(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    conn: psycopg.Connection[Any]
    with psycopg.connect(url) as conn:
        report = check_ingest(conn, args.index_version)
    print(report.model_dump_json())
    return 0 if report.clean else 1


def _kill_worker(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    command = [
        sys.executable,
        "-c",
        _RUN_CLI,
        "worker",
        "--database-url",
        url,
        "--lease",
        str(args.lease),
        "--heartbeat",
        str(args.heartbeat),
        "--poll",
        "0.5",
    ]

    def start(tag: str) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [*command, "--owner-tag", tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    plan = KillPlan(workers=args.workers, timeout_seconds=args.timeout)
    try:
        with PostgresQueueProbe.connect(
            url, kinds=[KIND], key_prefix=f"{args.index_version}:"
        ) as probe:
            kill = kill_worker_mid_job(probe, start, plan)
    except ChaosError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    conn: psycopg.Connection[Any]
    with psycopg.connect(url) as conn:
        integrity = check_ingest(conn, args.index_version)
    print(json.dumps({"kill": kill.model_dump(), "integrity": integrity.model_dump()}))
    code = record_rows(args, lambda date, sha: kill_rows(kill, integrity, date=date, git_sha=sha))
    return code or (0 if integrity.clean else 1)


def _load_rows(args: argparse.Namespace) -> int:
    try:
        data: object = json.loads(args.summary.read_text("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("k6 summary is not a JSON object")
        summary = parse_k6_summary(data)  # pyright: ignore[reportUnknownArgumentType]
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(summary.model_dump_json())
    return record_rows(
        args,
        lambda date, sha: load_rows(
            summary, date=date, git_sha=sha, system=args.system, config=args.config
        ),
    )
