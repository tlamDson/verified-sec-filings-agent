"""The 50 simulated accounts and the persona each one plays. Every account is test traffic."""

from collections import Counter

import pytest
from pydantic import ValidationError

from sec_agent.api.identity import Identity
from sec_agent.simusers.personas import PERSONAS
from sec_agent.simusers.roster import ACCOUNT_COUNT, SimAccount, roster


def test_there_are_fifty_accounts_sim_01_to_sim_50() -> None:
    accounts = roster(seed=7)
    assert ACCOUNT_COUNT == 50
    assert [a.email for a in accounts] == [f"sim-{n:02d}@example.com" for n in range(1, 51)]


def test_every_account_is_in_the_simulated_cohort() -> None:
    for account in roster(seed=7):
        assert account.user_id == f"sim:{account.email}"
        assert account.identity() == Identity(user_id=account.user_id, cohort="simulated")


def test_the_roster_is_fixed_by_its_seed() -> None:
    assert roster(seed=7) == roster(seed=7)
    assert [a.persona for a in roster(seed=7)] != [a.persona for a in roster(seed=8)]


def test_every_persona_plays_the_same_number_of_accounts() -> None:
    counts = Counter(a.persona for a in roster(seed=7))
    assert set(counts) == set(PERSONAS)
    assert len(set(counts.values())) == 1


@pytest.mark.parametrize("number", [0, 51])
def test_an_account_outside_1_to_50_is_refused(number: int) -> None:
    with pytest.raises(ValidationError):
        SimAccount(number=number, persona="student")
