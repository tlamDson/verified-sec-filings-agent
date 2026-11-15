"""`sec-agent agent init`: create the tables the agent keeps in Postgres."""

import argparse
from typing import TYPE_CHECKING, Any

import psycopg

from sec_agent.agent.checkpoint import postgres_checkpointer
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.llm.schema import apply_schema

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    agent = subparsers.add_parser("agent", help="manage the agent's tables")
    add_database_url_option(agent)
    commands = agent.add_subparsers(dest="agent_command", metavar="action", required=True)
    commands.add_parser(
        "init", help="create the LLM usage and conversation checkpoint tables"
    ).set_defaults(run=_init)


def _init(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    conn: psycopg.Connection[Any]
    with psycopg.connect(url, autocommit=True) as conn:
        apply_schema(conn)
    with postgres_checkpointer(url) as saver:
        saver.setup()
    print("agent schema ready")
    return 0
