#!/usr/bin/env bash
# The s-20 chaos run on the local Docker stack, in order:
#   1. ingest the test companies once with ONE worker (fills the raw cache; at most 10 req/s
#      to SEC, User-Agent from SEC_USER_AGENT)
#   2. re-ingest them into a second snapshot with 3 worker processes from that cache (no SEC
#      traffic), kill one mid-job, and check: no fact twice, every job closed
#   3. start 3 API replicas behind nginx and run k6 (200 simulated users by default);
#      kill api-2 at +90 s, rate-limit model llm-a at +150 s (fail over to llm-b) and llm-b
#      at +210 s (degraded mode), and restore both at +270 s
#   4. turn k6's summary into runs.csv rows (cohort simulated) in infra/load/results/
# Needs .env with POSTGRES_PASSWORD, API_AUTH_SECRET and SEC_USER_AGENT. Costs nothing: every
# model is `sec-agent chaos fake-llm`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infra/load/compose.yaml" --env-file "$ROOT/.env")
VERSION="${FACTS_VERSION:-v1}"
CHAOS_VERSION="${CHAOS_VERSION:-chaos1}"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
RESULTS="$ROOT/infra/load/results"
mkdir -p "$RESULTS"
# Written from containers by uid 1000 (workers) and k6's own user: open the bind mount.
chmod 0777 "$RESULTS"

# The test split of the golden company universe.
CIKS="${CIKS:-$(python -c "import json,sys; d=json.load(open(sys.argv[1])); print(' '.join(str(c['cik']) for c in d['companies'] if c['split']=='test' and not c['excluded']))" "$ROOT/data/golden/company_split.json")}"

run() { "${COMPOSE[@]}" run --rm --no-deps -v "$RESULTS:/results" worker-1 "$@"; }
mode() { curl -fsS -X PUT "http://127.0.0.1:$1/admin/mode" -H 'Content-Type: application/json' -d "{\"mode\": \"$2\", \"retry_after_seconds\": 30}" >/dev/null; }

echo "== build and start the database"
"${COMPOSE[@]}" --profile ingest build
"${COMPOSE[@]}" up -d --wait postgres

echo "== 1. ingest $VERSION with one worker (fills the raw cache)"
run sh -c "sec-agent jobs init && sec-agent xbrl init"
# shellcheck disable=SC2086
run sec-agent xbrl enqueue --index-version "$VERSION" $CIKS
run sec-agent worker --drain
run sec-agent chaos integrity --index-version "$VERSION"

echo "== 2. re-ingest into $CHAOS_VERSION with 3 workers and kill one mid-job"
# shellcheck disable=SC2086
run sec-agent xbrl enqueue --index-version "$CHAOS_VERSION" $CIKS
run sec-agent chaos kill-worker --index-version "$CHAOS_VERSION" --workers 3 \
  --record /results/runs.chaos.csv --git-sha "$SHA"

echo "== 3. 3 API replicas behind nginx, k6 with simulated users"
"${COMPOSE[@]}" up -d --wait llm-a llm-b api-1 api-2 api-3 lb
"${COMPOSE[@]}" --profile load run --rm k6 &
K6=$!
sleep 90 && echo "-- kill api-2" && "${COMPOSE[@]}" kill api-2
sleep 60 && echo "-- llm-a rate_limited" && mode 8181 rate_limited
sleep 60 && echo "-- llm-b rate_limited" && mode 8182 rate_limited
sleep 60 && echo "-- models back" && mode 8181 ok && mode 8182 ok
wait "$K6" || echo "k6 thresholds crossed (see the summary)"

echo "== 4. runs.csv rows"
run sec-agent chaos load-rows /results/summary.json --system api-x3+fake-llm \
  --config "PEAK_VUS=${PEAK_VUS:-200}; kill api-2 +90s; llm-a 429 +150s; llm-b 429 +210s" \
  --record /results/runs.load.csv --git-sha "$SHA"
echo "rows in $RESULTS/runs.chaos.csv and $RESULTS/runs.load.csv"
