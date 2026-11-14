"""The manifest of an exported reranker: what model it is and whose labels trained it."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_FILE = "reranker.json"
MODEL_FILE = "model.onnx"
TOKENIZER_FILE = "tokenizer.json"


class RerankerManifest(BaseModel):
    """Kept beside `model.onnx`. `trained_on` lists the companies whose G-ret labels
    trained the model (empty for an off-the-shelf model): a model must never be scored
    on questions about those companies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,99}$")
    base_model: str = Field(min_length=1)
    max_length: int = Field(ge=8, le=8192)
    trained_on: tuple[str, ...]
    onnx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training: dict[str, str | int | float] = {}
    parity_max_abs_diff: float | None = None
    """Largest |ONNX - torch| score over the export's check pairs."""
    created_at: dt.datetime
