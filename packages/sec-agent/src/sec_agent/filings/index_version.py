"""`index_version`: the name of one build of the text index.

The name is derived from everything that decides chunk content: the parser version and the
chunk configuration. Same code and configuration give the same name, so re-running a build
upserts into it; any change gives a new name, so the new build lands beside the old one
(blue/green) and queries pinned to the old name keep seeing the old rows.

Bump PARSER_VERSION whenever section detection or text extraction changes its output;
`test_output_is_pinned_to_the_parser_version` fails until you do.
"""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.filings.tokens import TOKENIZER_NAME

PARSER_VERSION = 1


class ChunkConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_tokens: int = Field(default=400, ge=20, le=2000)
    tokenizer: str = TOKENIZER_NAME


def index_version(config: ChunkConfig) -> str:
    """`chunks-p<parser>-t<max_tokens>-<8 hex digest of parser and config>`."""
    spec = {"parser": PARSER_VERSION, **config.model_dump()}
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:8]
    return f"chunks-p{PARSER_VERSION}-t{config.max_tokens}-{digest}"
