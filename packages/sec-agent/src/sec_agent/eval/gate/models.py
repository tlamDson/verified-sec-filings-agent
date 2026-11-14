"""What the gate measures and what it keeps as its baseline."""

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class GateMetric(BaseModel):
    """One number the gate watches, e.g. `N1:b2` (metric `N1`, system `b2`)."""

    model_config = _FROZEN

    name: str = Field(min_length=1)
    family: str = Field(min_length=1)
    """Which inputs it is measured on (`N1`, `A1`, `R1`, `S1`, `J1`)."""
    value: float
    n: int = Field(ge=0)
    higher_is_better: bool = True
    max_drop: float = Field(default=0.02, ge=0)
    """How far it may move the wrong way when its inputs were re-generated."""
    drift_only: bool = False
    """A breakdown (failures by kind): watched only while its inputs are unchanged, since a
    re-generated run may shift failures between kinds."""


class GateSnapshot(BaseModel):
    """A measurement, or the committed baseline: input digests by family, and the metrics."""

    model_config = _FROZEN

    inputs: dict[str, str]
    metrics: tuple[GateMetric, ...]
