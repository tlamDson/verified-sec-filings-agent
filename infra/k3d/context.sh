# Sourced by up.sh and hpa-watch.sh. Every kubectl and helm call goes to the k3d cluster's
# own context, never to whatever context is current, so the secrets from .env and the
# release can only reach this local cluster.
CTX="k3d-sec-agent"

kube() { kubectl --context "$CTX" "$@"; }

# Stops unless the context exists and the cluster it selects has its API server on this
# machine (k3d publishes it on 0.0.0.0, 127.0.0.1, localhost or host.docker.internal).
# `--minify --context` resolves the server through the context itself, so a local cluster
# that only shares the context's name cannot pass for it. The whole URL must match: scheme,
# local host, numeric port, nothing after but an optional slash.
LOCAL_SERVER='^https://(0\.0\.0\.0|127\.0\.0\.1|localhost|host\.docker\.internal):[0-9]+/?$'

require_context() {
  local server
  if ! server="$(kubectl config view --minify --context "$CTX"     -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)" || [ -z "$server" ]; then
    echo "no usable kube context $CTX: run infra/k3d/up.sh to create the cluster" >&2
    exit 1
  fi
  if ! [[ "$server" =~ $LOCAL_SERVER ]]; then
    echo "context $CTX points at $server, not a local k3d cluster: refusing" >&2
    exit 1
  fi
}
