# shellcheck shell=bash
# docker_pull_retry IMAGE [ATTEMPTS] [BASE_DELAY_SECONDS]
#
# Pull IMAGE, retrying with a growing pause. Anonymous pulls from Docker Hub on
# GitHub-hosted runners time out in bursts (auth.docker.io "Client.Timeout
# exceeded while awaiting headers", 2026-10-09: three failed release builds and
# several failed reserved-hosts jobs within an hour, all clean after a rerun).
# A pull that never succeeds still fails the step: this retries a transport
# flake, it does not turn a missing image into a pass.
#
# An image that is already present locally is not pulled again.
docker_pull_retry() {
  local image="$1" attempts="${2:-5}" delay="${3:-10}" n=1
  if docker image inspect "$image" >/dev/null 2>&1; then
    return 0
  fi
  while :; do
    if docker pull "$image"; then
      return 0
    fi
    if [ "$n" -ge "$attempts" ]; then
      echo "docker pull $image failed after $attempts attempts" >&2
      return 1
    fi
    echo "docker pull $image failed (attempt $n/$attempts), retrying in $((delay * n))s" >&2
    sleep "$((delay * n))"
    n=$((n + 1))
  done
}
