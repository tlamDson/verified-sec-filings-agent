"""Load an exported reranker directory: manifest, ONNX model, tokenizer.

The model file must have the SHA-256 its manifest records, so the served model is the one
the manifest (and the R1 rows measured with it) describe.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from sec_agent.rerank.models import MANIFEST_FILE, MODEL_FILE, TOKENIZER_FILE, RerankerManifest
from sec_agent.rerank.onnx_scorer import OnnxCrossEncoder


class RerankerLoadError(Exception):
    """The directory does not hold the reranker its manifest describes."""


@dataclass(frozen=True)
class LoadedReranker:
    manifest: RerankerManifest
    scorer: OnnxCrossEncoder


def load_reranker(
    directory: Path, *, batch_size: int = 16, threads: int | None = None
) -> LoadedReranker:
    manifest = read_manifest(directory)
    model, tokenizer = directory / MODEL_FILE, directory / TOKENIZER_FILE
    for path in (model, tokenizer):
        if not path.is_file():
            raise RerankerLoadError(f"{directory}: no {path.name}")
    if file_sha256(model) != manifest.onnx_sha256:
        raise RerankerLoadError(
            f"{model}: SHA-256 differs from the manifest; this is not the model it describes"
        )
    scorer = OnnxCrossEncoder(
        model,
        tokenizer,
        max_length=manifest.max_length,
        name=manifest.name,
        batch_size=batch_size,
        threads=threads,
    )
    return LoadedReranker(manifest=manifest, scorer=scorer)


def read_manifest(directory: Path) -> RerankerManifest:
    path = directory / MANIFEST_FILE
    try:
        return RerankerManifest.model_validate_json(path.read_text("utf-8"))
    except OSError as error:
        raise RerankerLoadError(f"{directory}: cannot read {MANIFEST_FILE}: {error}") from error
    except ValidationError as error:
        raise RerankerLoadError(f"{path}: not a reranker manifest: {error}") from error


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
