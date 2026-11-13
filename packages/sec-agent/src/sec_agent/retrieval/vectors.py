"""Vectors as pgvector text, checked first: a wrong shape never reaches the index."""

import math
from collections.abc import Sequence

from sec_agent.retrieval.errors import EmbeddingMismatchError
from sec_agent.retrieval.models import EmbedderSpec

UNIT_TOLERANCE = 1e-3  # |norm - 1| allowed for a normalised model (float32 rounding)


def check_vector(values: Sequence[float], spec: EmbedderSpec) -> None:
    if len(values) != spec.dimensions:
        raise EmbeddingMismatchError(
            f"{spec.model} returned {len(values)} dimensions; the space holds {spec.dimensions}"
        )
    if not all(math.isfinite(v) for v in values):
        raise EmbeddingMismatchError(f"{spec.model} returned a vector with non-finite values")
    if spec.normalized:
        norm = math.sqrt(sum(v * v for v in values))
        if abs(norm - 1.0) > UNIT_TOLERANCE:
            raise EmbeddingMismatchError(
                f"{spec.model} is declared normalised but returned a vector of norm {norm:.4f},"
                " not unit length"
            )


def vector_literal(values: Sequence[float], dimensions: int) -> str:
    """`[v1,v2,...]`, the text form pgvector parses."""
    if len(values) != dimensions:
        raise EmbeddingMismatchError(f"vector has {len(values)} dimensions, expected {dimensions}")
    return "[" + ",".join(repr(float(v)) for v in values) + "]"
