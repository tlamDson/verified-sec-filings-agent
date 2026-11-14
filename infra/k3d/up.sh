#!/usr/bin/env bash
# Bring up the optional Kubernetes deployment (s-x1) on k3d, in order:
#   1. create the k3d cluster (1 server, 2 agents) unless it exists
#   2. build the one app image (infra/load/Dockerfile) and import it into the cluster
#   3. make the namespace, the Postgres init ConfigMap (infra/postgres/init) and the Secret
#      (PGPASSWORD, API_AUTH_SECRET, SEC_USER_AGENT from .env; nothing is committed)
#   4. install the chart with the API off; the init job creates the tables
#   5. ingest the facts with the one worker (at most 10 req/s to SEC, User-Agent from
#      SEC_USER_AGENT; a second run reads the raw cache volume)
#   6. turn the API on: 2-5 replicas under the HPA, behind Traefik on 127.0.0.1:8090
# Models are simulated (`sec-agent chaos fake-llm`) unless the chart's llm.providers is
# overridden, so nothing here can bill. Needs docker, k3d, kubectl and helm.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NS="${NAMESPACE:-sec-agent}"
RELEASE="${RELEASE:-sec-agent}"
SECRET="$RELEASE-secrets"
IMAGE="sec-agent-load:local"
VERSION="${FACTS_VERSION:-v1}"
CHART="$ROOT/infra/helm/sec-agent"

# Only the three keys the chart needs are read from .env.
env_value() { grep -E "^$1=" "$ROOT/.env" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
PGPASSWORD="$(env_value POSTGRES_PASSWORD)"
API_AUTH_SECRET="$(env_value API_AUTH_SECRET)"
SEC_USER_AGENT="$(env_value SEC_USER_AGENT)"
: "${PGPASSWORD:?set POSTGRES_PASSWORD in .env (see .env.example)}"
: "${API_AUTH_SECRET:?set API_AUTH_SECRET in .env (see .env.example)}"
: "${SEC_USER_AGENT:?set SEC_USER_AGENT in .env (see .env.example)}"

# The test split of the golden company universe, as in infra/load/chaos.sh.
CIKS="${CIKS:-$(python -c "import json,sys; d=json.load(open(sys.argv[1])); print(' '.join(str(c['cik']) for c in d['companies'] if c['split']=='test' and not c['excluded']))" "$ROOT/data/golden/company_split.json")}"

echo "== 1. cluster"
if ! k3d cluster list sec-agent >/dev/null 2>&1; then
  k3d cluster create --config "$ROOT/infra/k3d/cluster.yaml"
fi

echo "== 2. image"
docker build -f "$ROOT/infra/load/Dockerfile" -t "$IMAGE" "$ROOT"
k3d image import "$IMAGE" --cluster sec-agent

echo "== 3. namespace, init SQL, secret"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" create configmap sec-agent-pg-init --from-file="$ROOT/infra/postgres/init" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" create secret generic "$SECRET" \
  --from-literal=PGPASSWORD="$PGPASSWORD" \
  --from-literal=API_AUTH_SECRET="$API_AUTH_SECRET" \
  --from-literal=SEC_USER_AGENT="$SEC_USER_AGENT" \
  --dry-run=client -o yaml | kubectl apply -f -

HELM=(helm upgrade --install "$RELEASE" "$CHART" -n "$NS" --set secretName="$SECRET"
  --set factsVersion="$VERSION" --wait --timeout 10m)

echo "== 4. database, worker, simulated models (API off)"
"${HELM[@]}" --set api.enabled=false

echo "== 5. ingest $VERSION with the one worker"
# shellcheck disable=SC2086
kubectl -n "$NS" exec "deploy/$RELEASE-worker" -- sec-agent xbrl enqueue --index-version "$VERSION" $CIKS
# The deployed worker takes the jobs; wait until none is queued or running.
while kubectl -n "$NS" exec "deploy/$RELEASE-worker" -- sec-agent jobs stats |
  grep -Eq '^(queued|running) [1-9]'; do
  sleep 15
done
kubectl -n "$NS" exec "deploy/$RELEASE-worker" -- sec-agent chaos integrity --index-version "$VERSION"

echo "== 6. API on, under the HPA"
"${HELM[@]}" --set api.enabled=true
kubectl -n "$NS" get hpa,deploy,pods
echo "API: curl http://127.0.0.1:8090/healthz ; HPA under load: infra/k3d/hpa-watch.sh"
