"""`sec-agent mcp` as a client launches it: a subprocess speaking MCP over stdin and stdout.

Facts are the recorded Apple companyfacts, in a throwaway local Postgres; no network.
"""

import sys

import pytest
from mcp import Client, StdioServerParameters
from tools_data import APPLE_CIK, FACTS_VERSION

from sec_agent.xbrl.models import Fact, NormalizationReport
from sec_agent.xbrl.normalize import Normalized
from sec_agent.xbrl.store import PostgresFactStore

pytestmark = pytest.mark.anyio

_LAUNCH = "import sys; from sec_agent.cli import main; sys.exit(main(sys.argv[1:]))"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_stdio_server_answers_a_tool_call(
    tools_db: str, recorded_facts: dict[int, list[Fact]]
) -> None:
    with PostgresFactStore.connect(tools_db) as store:
        store.write(
            index_version=FACTS_VERSION,
            cik=APPLE_CIK,
            entity_name="Apple Inc.",
            normalized=Normalized(facts=recorded_facts[APPLE_CIK], report=NormalizationReport()),
        )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", _LAUNCH, "mcp", "--database-url", tools_db, "--facts-version", FACTS_VERSION],
    )
    async with Client(params, read_timeout_seconds=60) as client:
        listed = await client.list_tools()
        result = await client.call_tool(
            "compute_ratio", {"company": "Apple", "ratio": "gross_margin", "fiscal_year": 2024}
        )
    assert len(listed.tools) == 5
    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["value"] == "46.206350"
