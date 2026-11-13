#!/bin/sh
# Entry point of the Space: create the agent and API tables (idempotent), then serve one
# replica. DATABASE_URL, API_AUTH_SECRET and LLM_PROVIDERS are Space secrets; FACTS_VERSION
# (default v1) is a Space variable. The facts must already be loaded into the database.
set -eu
: "${DATABASE_URL:?set DATABASE_URL as a Space secret}"
sec-agent agent init
sec-agent api init
exec sec-agent api serve --facts-version "${FACTS_VERSION:-v1}" --lexical --host 0.0.0.0 --port "${PORT:-7860}"
