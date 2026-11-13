# CLAUDE.md

The rules for this repository live in AGENTS.md, shared with every other agent:

@AGENTS.md

## Claude-specific notes

- On Windows, run uv as `python -m uv` when `uv` is not on PATH.
- A read-only subagent may only locate code and must return a short list of files and functions; write tests and code yourself.
- While working, run only the checks that cover what you changed, with quiet output (`-q`). Run the full set once before pushing.
