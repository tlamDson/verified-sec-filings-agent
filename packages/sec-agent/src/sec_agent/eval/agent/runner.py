"""Run a system over A1 scenarios with the same cache discipline as the numeric runner.

Every transcript is appended to `SYSTEM.cache.jsonl` as it arrives; a rerun plays only the
scenarios whose (id, model, scenario and prompt hash) has no cached transcript. The results
file `SYSTEM.jsonl` is then rewritten with exactly one transcript per scenario, for this
run's model and prompt, so what is scored is always what was asked for. Each transcript of
the results file also names the tools the system offered and, given an oracle, the
expected calls' results.
"""

import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import Scenario, Transcript, scenario_sha256
from sec_agent.eval.agent.systems import ScenarioSystem
from sec_agent.eval.numeric.runner import RunSummary, cache_path
from sec_agent.golden.jsonl import append_jsonl, read_jsonl, write_jsonl


def run_scenarios(
    scenarios: Sequence[Scenario],
    system: ScenarioSystem,
    *,
    results: Path,
    now: Callable[[], dt.datetime],
    oracle: Callable[[Scenario], tuple[Evidence, ...]] | None = None,
) -> RunSummary:
    """`oracle`: the scorer's own run of the checks' calls (`systems.oracle_calls`), kept in
    every transcript of the results file, cached or new; it costs no model call."""
    cache = cache_path(results)
    existing = read_jsonl(cache, Transcript)
    others = sorted({t.system for t in existing} - {system.name})
    if others:
        raise ValueError(f"{cache} holds transcripts of {others}, not of {system.name}")
    done = {(t.scenario_id, t.model, t.scenario_sha256): t for t in existing}
    fingerprint = system.fingerprint
    current: list[Transcript] = []
    asked = cached = 0
    for scenario in scenarios:
        key = (scenario.id, system.model, scenario_sha256(scenario, fingerprint))
        transcript = done.get(key)
        if transcript is not None:
            cached += 1
        else:
            turn = system.play(scenario)
            transcript = Transcript(
                scenario_id=scenario.id,
                system=system.name,
                model=system.model,
                scenario_sha256=key[2],
                text=turn.text,
                status=turn.status,
                evidence=turn.evidence,
                asked_on=system.asked_on,
                answered_at=now(),
                offered_tools=system.offered_tools,
            )
            append_jsonl(cache, transcript)
            done[key] = transcript
            asked += 1
        update: dict[str, object] = {"offered_tools": system.offered_tools}
        if oracle is not None:
            update["oracle"] = oracle(scenario)
        current.append(transcript.model_copy(update=update))
    write_jsonl(results, current)
    return RunSummary(asked=asked, cached=cached)
