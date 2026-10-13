#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
image=${1:?Pass the immutable GHCR image tag or digest}
case "$image" in
  ghcr.io/quackudy/2110471-computer-network-i-websocket-project:*) ;;
  ghcr.io/quackudy/2110471-computer-network-i-websocket-project@sha256:*) ;;
  *) echo 'Unexpected image repository' >&2; exit 1 ;;
esac
# The workflow passes its short-lived token on stdin, never in an argument or file.
IFS= read -r registry_token
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf "$DOCKER_CONFIG"' EXIT
printf '%s' "$registry_token" | docker login ghcr.io -u Quackudy --password-stdin >/dev/null
unset registry_token
compose=(docker compose -f compose.yml -f compose.oracle.yml)
previous=$(cat .image 2>/dev/null || true)
export APP_IMAGE="$image"
"${compose[@]}" pull app ollama model-pull
if ! "${compose[@]}" up -d --no-build --wait --wait-timeout 600; then
  echo 'Deployment failed; restoring the previous application image.' >&2
  if [[ -n "$previous" ]]; then
    APP_IMAGE="$previous" "${compose[@]}" up -d --no-build --wait --wait-timeout 90
  fi
  exit 1
fi
curl --fail --silent --show-error --retry 5 --retry-delay 2 http://127.0.0.1:8080/healthz
printf '%s\n' "$image" > .image
echo 'Relay deployment is healthy.'
