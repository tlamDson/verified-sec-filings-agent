#!/usr/bin/env bash
# Load the API in the k3d cluster and watch the HPA scale it (s-x1). The load is the s-20 k6
# script (infra/load/chat.js) run in a pod against the API service: every request is a
# simulated account (sim:load-NNN) asking a simulated model, so what it shows is simulated
# and says nothing about answer quality. Replica counts are logged to
# infra/k3d/results/hpa.log as observations; none of them is a runs.csv number.
# Needs the deployment from infra/k3d/up.sh. PEAK_VUS (default 50) sets the load.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NS="${NAMESPACE:-sec-agent}"
RELEASE="${RELEASE:-sec-agent}"
SECRET="$RELEASE-secrets"
PEAK_VUS="${PEAK_VUS:-50}"
RESULTS="$ROOT/infra/k3d/results"
mkdir -p "$RESULTS"

echo "== API up?"
curl -fsS http://127.0.0.1:8090/healthz >/dev/null

echo "== k6 pod, $PEAK_VUS simulated users"
kubectl -n "$NS" create configmap sec-agent-k6 --from-file="$ROOT/infra/load/chat.js" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" delete pod sec-agent-k6 --ignore-not-found
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: sec-agent-k6
  labels:
    sec-agent/simulated: "true"
spec:
  restartPolicy: Never
  containers:
    - name: k6
      image: grafana/k6:1.0.0
      args: ["run", "/scripts/chat.js"]
      env:
        - name: BASE_URL
          value: http://$RELEASE-api:8000
        - name: PEAK_VUS
          value: "$PEAK_VUS"
        - name: API_AUTH_SECRET
          valueFrom:
            secretKeyRef:
              name: $SECRET
              key: API_AUTH_SECRET
      volumeMounts:
        - name: scripts
          mountPath: /scripts
  volumes:
    - name: scripts
      configMap:
        name: sec-agent-k6
EOF

echo "== HPA every 15 s until k6 ends (log: $RESULTS/hpa.log)"
: >"$RESULTS/hpa.log"
while true; do
  phase="$(kubectl -n "$NS" get pod sec-agent-k6 -o jsonpath='{.status.phase}')"
  { date -u +%FT%TZ; kubectl -n "$NS" get hpa "$RELEASE-api" --no-headers; } | paste -sd' ' | tee -a "$RESULTS/hpa.log"
  case "$phase" in Succeeded | Failed) break ;; esac
  sleep 15
done
kubectl -n "$NS" logs sec-agent-k6 | tail -n 40
echo "k6 pod: $phase"
[ "$phase" = Succeeded ]
