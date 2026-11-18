# Contributing

Thanks for helping. The rules every contributor and coding agent follows are in [AGENTS.md](AGENTS.md).

## Run it locally

Follow the Development section of the [README.md](README.md): Python 3.12 with uv, Node 22 with pnpm, and Docker for the local database.

## Branches and pull requests

- Branch from `develop` and open your pull request against `develop`.
- Start the PR title with its type: `feat:`, `fix:`, `test:`, `docs:` or `chore:`.
- Write the failing tests first: the first commit of a PR contains only those tests.
- Tests never call SEC, an LLM or the network; use recorded fixtures.

## Checks that must pass

CI runs two required checks, `Python checks` and `Web checks`. Run them locally before you push:

```sh
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest -q
uv run sec-agent eval gate
pnpm biome check
pnpm typecheck
pnpm test
```

## Conduct

Please read the [code of conduct](.github/CODE_OF_CONDUCT.md).
