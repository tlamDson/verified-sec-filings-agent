"""LLMRouter: what an answered call is charged against the daily token quota.

A reply's usage replaces the call's hold only when it is complete. A usage that leaves a
count out would otherwise return most of the hold for tokens that were spent, and the
day's quota would be passed without the count ever showing it.
The providers are scripted or answered by `httpx.MockTransport` (simulated replies).
"""

import httpx
import pytest
from llm_fakes import Clock, ScriptedProvider, fixture_json, says

from sec_agent.llm.messages import ChatRequest, Usage
from sec_agent.llm.openai_compat import OpenAICompatProvider
from sec_agent.llm.provider import ProviderConfig
from sec_agent.llm.quota import MemoryQuotaStore, QuotaLimits
from sec_agent.llm.router import LLMRouter
from sec_agent.llm.token_bound import token_bound

CAPPED = ChatRequest(messages=[{"role": "user", "content": "question"}], max_tokens=64)
TOKENS = QuotaLimits(tokens_per_day=10_000)


def _bound(request: ChatRequest) -> int:
    bound = token_bound(request)
    assert bound is not None
    return bound


def _charged(usage: Usage, limits: QuotaLimits = TOKENS) -> int:
    """The day's tokens after one answered call that reported `usage`."""
    clock, quota = Clock(), MemoryQuotaStore()
    provider = ScriptedProvider("a", [says("ok")], limits=limits, usage=usage)
    LLMRouter([provider], quota=quota, clock=clock.monotonic, now=clock.now).complete(CAPPED)
    return quota.usage("a", clock.now()).day_tokens


@pytest.mark.parametrize(
    "counts",
    [
        {"prompt_tokens": 40, "completion_tokens": 0},
        {"prompt_tokens": 0, "completion_tokens": 7},
        {"prompt_tokens": 1, "completion_tokens": 0},
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 47},
        {"prompt_tokens": 40, "completion_tokens": 0, "total_tokens": 47},
    ],
)
def test_a_reply_whose_usage_leaves_a_count_out_is_charged_its_whole_bound(
    counts: dict[str, int],
) -> None:
    assert _bound(CAPPED) > 47
    assert _charged(Usage(**counts)) == _bound(CAPPED)


def test_an_incomplete_usage_above_the_bound_is_charged_what_it_reports() -> None:
    over = _bound(CAPPED) + 500
    assert _charged(Usage(prompt_tokens=over, completion_tokens=0)) == over


def test_a_complete_usage_is_charged_its_total_when_that_is_above_its_parts() -> None:
    assert _charged(Usage(prompt_tokens=40, completion_tokens=7)) == 47
    assert _charged(Usage(prompt_tokens=40, completion_tokens=7, total_tokens=90)) == 90


def test_without_a_token_quota_an_incomplete_usage_counts_what_it_reports() -> None:
    """Nothing is held for such a provider; the day's tokens are history, not a limit."""
    assert _charged(Usage(prompt_tokens=40, completion_tokens=0), QuotaLimits()) == 40


def test_repeated_incomplete_usage_closes_the_provider_at_its_token_quota() -> None:
    """Each call spends its bound of the day, so the quota is reached, not slipped past."""
    clock, quota = Clock(), MemoryQuotaStore()
    bound = _bound(CAPPED)
    limits = QuotaLimits(tokens_per_day=3 * bound)
    partial = ScriptedProvider(
        "a", [says("1"), says("2"), says("3")], limits=limits, usage=Usage(1, 0)
    )
    backup = ScriptedProvider("b", [says("from b")])
    router = LLMRouter([partial, backup], quota=quota, clock=clock.monotonic, now=clock.now)
    assert [router.complete(CAPPED).provider for _ in range(4)] == ["a", "a", "a", "b"]
    assert quota.usage("a", clock.now()).day_tokens == 3 * bound
    assert len(partial.requests) == 3


@pytest.mark.parametrize(
    "reported",
    [
        {"prompt_tokens": 3},
        {"completion_tokens": 3},
        {"prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 3},
        {"prompt_tokens": "120", "completion_tokens": 14},
    ],
)
def test_an_incomplete_usage_on_the_wire_is_charged_the_whole_bound(reported: object) -> None:
    payload = fixture_json("chat_answer.sim.json")
    payload["usage"] = reported
    config = ProviderConfig(
        name="sim-a", base_url="https://llm.example.com/v1", model="sim-model-a", limits=TOKENS
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    clock, quota = Clock(), MemoryQuotaStore()
    with OpenAICompatProvider(config, transport=transport) as provider:
        LLMRouter([provider], quota=quota, clock=clock.monotonic, now=clock.now).complete(CAPPED)
    assert quota.usage("sim-a", clock.now()).day_tokens == _bound(CAPPED)
