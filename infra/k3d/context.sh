# Sourced by up.sh and hpa-watch.sh. Every kubectl and helm call goes to the k3d cluster's
# own context, never to whatever context is current, so the secrets from .env and the
# release can only reach this local cluster.
CTX="k3d-sec-agent"

kube() { kubectl --context "$CTX" "$@"; }

# Stops unless the context exists and its API server is on this machine (k3d publishes it on
# 0.0.0.0, 127.0.0.1, localhost or host.docker.internal).
require_context() {
  local server
  server="$(kubectl config view -o jsonpath="{.clusters[?(@.name==\"$CTX\")].cluster.server}")"
  if [ -z "$server" ]; then
    echo "no kube context $CTX: run infra/k3d/up.sh to create the cluster" >&2
    exit 1
  fi
  case "$server" in
    https://0.0.0.0:* | https://127.0.0.1:* | https://localhost:* | https://host.docker.internal:*) ;;
    *)
      echo "context $CTX points at $server, not a local k3d cluster: refusing" >&2
      exit 1
      ;;
  esac
}
