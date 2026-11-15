"""The 50 simulated accounts, `sim-01@example.com` to `sim-50@example.com`, and the persona
each plays. These are the only addresses the web app's simulated sign-in accepts
(example.com is reserved for testing, RFC 2606); there is no user table to seed, so the
roster is the seed: fixed by a number, the same on every run.
"""

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.api.identity import SIMULATED_PREFIX, Identity
from sec_agent.golden.ranking import seeded_key
from sec_agent.simusers.personas import PERSONAS, PersonaName

ACCOUNT_COUNT = 50


class SimAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int = Field(ge=1, le=ACCOUNT_COUNT)
    persona: PersonaName

    @property
    def email(self) -> str:
        return f"sim-{self.number:02d}@example.com"

    @property
    def user_id(self) -> str:
        return f"{SIMULATED_PREFIX}{self.email}"

    def identity(self) -> Identity:
        return Identity(user_id=self.user_id, cohort="simulated")


def roster(seed: int) -> tuple[SimAccount, ...]:
    """Accounts in number order; personas dealt in turn over a seeded order of the
    accounts, so every persona plays the same number of accounts."""
    names: list[PersonaName] = sorted(PERSONAS)
    numbers = sorted(range(1, ACCOUNT_COUNT + 1), key=lambda n: seeded_key(seed, "account", n))
    persona: dict[int, PersonaName] = {n: names[i % len(names)] for i, n in enumerate(numbers)}
    return tuple(SimAccount(number=n, persona=persona[n]) for n in range(1, ACCOUNT_COUNT + 1))
