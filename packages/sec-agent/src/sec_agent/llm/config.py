"""Providers from the environment.

`LLM_PROVIDERS` is a JSON list of provider objects, tried in the order listed. Without it
the only provider is a local llama.cpp server, which costs nothing. A key is never in the
list: `api_key_env` names the variable that holds it, so the list itself can be shared.
"""

import json
from collections.abc import Mapping
from typing import Any, cast

import httpx
from pydantic import ValidationError

from sec_agent.llm.errors import LLMConfigError
from sec_agent.llm.openai_compat import OpenAICompatProvider
from sec_agent.llm.provider import ProviderConfig

PROVIDERS_ENV_VAR = "LLM_PROVIDERS"
DEFAULT_PROVIDERS: tuple[ProviderConfig, ...] = (
    ProviderConfig(
        name="local",
        base_url="http://127.0.0.1:8080/v1",
        model="local",
        timeout_seconds=300.0,
    ),
)


def providers_from_env(environ: Mapping[str, str]) -> tuple[ProviderConfig, ...]:
    text = environ.get(PROVIDERS_ENV_VAR, "").strip()
    if not text:
        return DEFAULT_PROVIDERS
    try:
        raw: object = json.loads(text)
    except ValueError as error:
        raise LLMConfigError(f"{PROVIDERS_ENV_VAR} is not JSON") from error
    if not isinstance(raw, list):
        raise LLMConfigError(f"{PROVIDERS_ENV_VAR} must be a JSON list of providers")
    items = cast(list[object], raw)
    if not items:
        raise LLMConfigError(f"{PROVIDERS_ENV_VAR} lists no provider")
    providers = tuple(_provider(index, item) for index, item in enumerate(items))
    seen: set[str] = set()
    for provider in providers:
        if provider.name in seen:
            raise LLMConfigError(f"{PROVIDERS_ENV_VAR} lists provider {provider.name!r} twice")
        seen.add(provider.name)
    return providers


def build_providers(
    configs: tuple[ProviderConfig, ...],
    environ: Mapping[str, str],
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[OpenAICompatProvider, ...]:
    """One HTTP provider per configuration, in order, each with its key from `environ`."""
    keys = [_api_key(config, environ) for config in configs]
    return tuple(
        OpenAICompatProvider(config, api_key=key, transport=transport)
        for config, key in zip(configs, keys, strict=True)
    )


def _provider(index: int, item: object) -> ProviderConfig:
    try:
        return ProviderConfig.model_validate(item)
    except ValidationError as error:
        problems = "; ".join(_problem(e["loc"], e["msg"]) for e in error.errors())
        raise LLMConfigError(f"{PROVIDERS_ENV_VAR}[{index}]: {problems}") from None


def _problem(loc: tuple[Any, ...], message: str) -> str:
    """The field and what is wrong with it, never the value (it may be a pasted key)."""
    return f"{'.'.join(str(part) for part in loc) or 'provider'}: {message}"


def _api_key(config: ProviderConfig, environ: Mapping[str, str]) -> str | None:
    if config.api_key_env is None:
        return None
    key = environ.get(config.api_key_env, "").strip()
    if not key:
        raise LLMConfigError(
            f"provider {config.name!r} needs its key in the variable {config.api_key_env}"
        )
    return key
