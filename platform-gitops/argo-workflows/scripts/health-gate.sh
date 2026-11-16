#!/bin/sh
# Usage:
#   health-gate.sh <checkout> <team> <component> <commit>
#
# Post-sync health gate for deploy-service (mctlhq/mctl-gitops#2653). A deploy
# is green only when the platform has seen the new version running, not when
# its commit was pushed. Every service gets the same check, worker or not:
#
#   1. Argo CD: Application <team>-<component> is Synced and Healthy at a
#      revision that contains <commit>.
#   2. Runtime: every pod of the release's main container runs the image
#      digest the committed values resolve to (the imageID kubelet recorded,
#      not anything the application says about itself), all pods belong to
#      one ReplicaSet, and all are ready.
#   3. Stability: the same pods are still ready, with no new restarts, after
#      $HG_STABLE seconds.
#   4. HTTP, only for a service with a public host and a readiness probe:
#      https://<host><readiness path> answers 2xx. A 5xx or no answer keeps
#      the gate waiting. A redirect, 401 or 403 is an auth wall or an alias
#      host in front of the service (Cloudflare Access, forward-auth, a
#      domain that redirects to the canonical one): the route answered but the
#      application was not reached, so HTTP is reported as not verified and
#      the verdict rests on 1-3. kubelet's readiness probe has already asked
#      the same path from inside the cluster.
#
# The expected digest is image.digest from the values at <commit> when set,
# otherwise what repository:tag resolves to in the registry now
# (check-image-user.sh resolve-digest, the tenant pull secret via
# $DOCKER_CONFIG_JSON). A tag pushed again between kubelet's pull and this
# read shows up as a mismatch: red, which is the truth.
#
# Could not observe is never observed healthy: an unreadable Application,
# pod list, registry or values file keeps the gate waiting, and when the
# deadline passes the result is "unknown" and the exit code non-zero.
#
# Results (written to $HG_OUT_DIR, default /tmp/health-gate):
#   health        healthy | idle | unhealthy | unknown
#                 idle: Argo CD applied the commit and the release is scaled
#                 to zero on purpose (every Deployment wants 0 replicas and
#                 autoscaling is off), so nothing runs that could be checked.
#                 It is not a health claim, and says so.
#   health_url    https://<host> for a service with a public host, else ""
#   argo_revision the gitops revision Argo CD reported Synced and Healthy
#   image_digest  the digest the pods were verified to run
#   reason        one line, why the gate ended where it did
#
# Exit 0 for healthy and idle. 1: unhealthy or unknown at the deadline. 2: bad
# input.
#
# Tunables (seconds): HG_TIMEOUT (600), HG_INTERVAL (10), HG_STABLE (60).
# HG_RESOLVE overrides the digest resolver command (tests). HG_NO_REFRESH=1
# skips the Argo CD refresh request, leaving the gate read-only.
#
# POSIX sh plus kubectl, git, jq, yq (mikefarah's) and curl: alpine/k8s.
set -u

die() { echo "health-gate: $1" >&2; exit 2; }

[ "$#" -eq 4 ] || die "usage: $0 <checkout> <team> <component> <commit>"
CHECKOUT=$1
TEAM=$2
COMPONENT=$3
COMMIT=$4

# Names become kubectl selectors and paths; the commit becomes a git revision.
for v in "$TEAM" "$COMPONENT"; do
  case "$v" in
    ""|-*|*[!a-z0-9-]*) die "invalid team or component name: $v" ;;
  esac
done
case "$COMMIT" in
  *[!0-9a-f]*) die "commit must be 40 lowercase hex: $COMMIT" ;;
esac
[ "${#COMMIT}" -eq 40 ] || die "commit must be 40 lowercase hex: $COMMIT"

TIMEOUT=${HG_TIMEOUT:-600}
INTERVAL=${HG_INTERVAL:-10}
STABLE=${HG_STABLE:-60}
OUT=${HG_OUT_DIR:-/tmp/health-gate}
APP="${TEAM}-${COMPONENT}"
NS=$TEAM
CONTAINER=base-service  # the chart's main container ({{ .Chart.Name }})
SCRIPTS="${CHECKOUT}/platform-gitops/argo-workflows/scripts"
RESOLVE=${HG_RESOLVE:-"sh ${SCRIPTS}/check-image-user.sh resolve-digest"}

mkdir -p "$OUT" || die "cannot create ${OUT}"
TMP=$(mktemp -d) || die "mktemp failed"
trap 'rm -rf "$TMP"' EXIT

# Nothing is written as healthy until every check passed; a crash mid-way
# leaves "unknown", not a stale or empty verdict.
for f in health_url argo_revision image_digest; do : > "${OUT}/${f}"; done
echo unknown > "${OUT}/health"
echo "gate did not finish" > "${OUT}/reason"

finish() {
  # finish <health> <reason>
  echo "$1" > "${OUT}/health"
  echo "$2" > "${OUT}/reason"
  case "$1" in
    healthy|idle) echo "$(echo "$1" | tr '[:lower:]' '[:upper:]'): ${APP}: $2"; exit 0 ;;
    *) echo "$(echo "$1" | tr '[:lower:]' '[:upper:]'): ${APP}: $2" >&2; exit 1 ;;
  esac
}

# ── Effective values at the deployed commit ─────────────────────────────────
# The chart's defaults overlaid with the service's values (jq `*` merges
# objects recursively; an explicit null in the service, such as
# `probes.readiness: null`, wins). Read once: the commit does not change.
CHART_PATH="platform-gitops/helm-charts/base-service/values.yaml"
SVC_PATH="platform-gitops/services/${TEAM}/${COMPONENT}/values.yaml"
show_at_commit() {
  git -C "$CHECKOUT" show "${COMMIT}:$1" > "$2" 2> "$TMP/git.err" \
    || { cat "$TMP/git.err" >&2; die "cannot read $1 at ${COMMIT}"; }
}
show_at_commit "$CHART_PATH" "$TMP/chart.yaml"
show_at_commit "$SVC_PATH" "$TMP/svc.yaml"
yq -o json '.' "$TMP/chart.yaml" > "$TMP/chart.json" || die "cannot parse ${CHART_PATH} at ${COMMIT}"
yq -o json '. // {}' "$TMP/svc.yaml" > "$TMP/svc.json" || die "cannot parse ${SVC_PATH} at ${COMMIT}"
jq -s '.[0] * .[1]' "$TMP/chart.json" "$TMP/svc.json" > "$TMP/values.json" || die "cannot merge values"

# The image comes from the service's own file and is read as written: through
# JSON an unquoted tag such as 1.10 would turn into the number 1.1.
repo=$(yq '.image.repository // ""' "$TMP/svc.yaml") || die "cannot read image.repository"
tag=$(yq '.image.tag // ""' "$TMP/svc.yaml") || die "cannot read image.tag"
pinned=$(yq '.image.digest // ""' "$TMP/svc.yaml") || die "cannot read image.digest"
case "${repo}:${tag}" in
  *[!A-Za-z0-9._:/@-]*) die "unexpected image reference: ${repo}:${tag}" ;;
esac
[ -n "$repo" ] && [ -n "$tag" ] || die "${SVC_PATH} at ${COMMIT} names no image.repository and image.tag"

host=""
if [ "$(jq -r '.ingress.enabled == true' "$TMP/values.json")" = true ]; then
  host=$(jq -r '(.ingress.host // "") as $h | if $h != "" then $h else (.ingress.hosts[0] // "") end' "$TMP/values.json")
fi
case "$host" in
  "") ;;
  *[!a-z0-9.-]*) die "unexpected ingress host: ${host}" ;;
esac
# The readiness path is what the platform already considers "ready"; a probe
# nulled out (a worker with no HTTP endpoint) means there is no path to ask.
ready_path=$(jq -r '.probes.readiness.path // ""' "$TMP/values.json")
case "$ready_path" in
  "") ;;
  /*) case "$ready_path" in *[!A-Za-z0-9/._~-]*) die "unexpected readiness path: ${ready_path}" ;; esac ;;
  *) die "unexpected readiness path: ${ready_path}" ;;
esac

[ -n "$host" ] && echo "https://${host}" > "${OUT}/health_url"

valid_digest() {
  case "$1" in
    sha256:*) h=${1#sha256:} ;;
    *) return 1 ;;
  esac
  case "$h" in *[!0-9a-f]*) return 1 ;; esac
  [ "${#h}" -eq 64 ]
}

if [ -n "$pinned" ]; then
  valid_digest "$pinned" || die "image.digest is not sha256:<64 hex>: ${pinned}"
fi

# ── Observation ─────────────────────────────────────────────────────────────
# Each probe sets $why to the reason it is not yet satisfied and returns 1;
# `unknown` marks a read that failed, as opposed to a state that is wrong.
why=""
state=unknown

expected=""
resolve_expected() {
  [ -n "$expected" ] && return 0
  if [ -n "$pinned" ]; then expected=$pinned; return 0; fi
  if ! d=$($RESOLVE "${repo}:${tag}" 2> "$TMP/resolve.err"); then
    why="cannot resolve ${repo}:${tag} in its registry: $(tail -1 "$TMP/resolve.err")"; state=unknown; return 1
  fi
  valid_digest "$d" || { why="resolver gave a malformed digest for ${repo}:${tag}: ${d}"; state=unknown; return 1; }
  expected=$d
}

revision=""
check_argo() {
  if ! kubectl -n argocd get application "$APP" -o json > "$TMP/app.json" 2> "$TMP/kubectl.err"; then
    why="cannot read Application ${APP}: $(tail -1 "$TMP/kubectl.err")"; state=unknown; return 1
  fi
  sync=$(jq -r '.status.sync.status // ""' "$TMP/app.json") || { why="unreadable Application ${APP}"; state=unknown; return 1; }
  health=$(jq -r '.status.health.status // ""' "$TMP/app.json")
  # Multi-source Applications (the apps ApplicationSet) report revisions[];
  # a single-source one reports revision. Every source is this repository.
  revs=$(jq -r '(.status.sync.revisions // [.status.sync.revision // empty])[]' "$TMP/app.json")
  [ -n "$revs" ] || { why="Application ${APP} reports no sync revision"; state=unknown; return 1; }
  for r in $revs; do
    case "$r" in *[!0-9a-f]*|"") why="Application ${APP} reports a non-commit revision: ${r}"; state=unknown; return 1 ;; esac
    if ! git -C "$CHECKOUT" cat-file -e "${r}^{commit}" 2>/dev/null; then
      git -C "$CHECKOUT" fetch -q origin "$r" 2>/dev/null \
        || { why="cannot fetch revision ${r} to compare with ${COMMIT}"; state=unknown; return 1; }
    fi
    if ! git -C "$CHECKOUT" merge-base --is-ancestor "$COMMIT" "$r" 2>/dev/null; then
      why="Argo CD is at ${r}, which does not contain ${COMMIT} yet"; state=waiting; return 1
    fi
  done
  revision=$(echo "$revs" | head -1)
  [ "$sync" = Synced ] || { why="Application ${APP} is ${sync:-without a sync status} at ${revision}"; state=waiting; return 1; }
  [ "$health" = Healthy ] || { why="Application ${APP} is ${health:-without a health status} at ${revision}"; state=waiting; return 1; }
  return 0
}

# Prints one line per pod of the release's ReplicaSets that is neither
# terminating nor finished: name, pod-template-hash, digest the main
# container runs, ready, restarts. Evicted and completed pods (phase Failed
# or Succeeded) are history, not the running version.
list_pods() {
  kubectl -n "$NS" get pods -l "app.kubernetes.io/instance=${APP}" -o json > "$TMP/pods.json" 2> "$TMP/kubectl.err" \
    || return 1
  jq -r --arg c "$CONTAINER" '
    .items[]
    | select(.metadata.deletionTimestamp == null)
    | select((.metadata.ownerReferences // []) | any(.kind == "ReplicaSet"))
    | select(.status.phase != "Failed" and .status.phase != "Succeeded")
    | . as $p
    | ([.status.containerStatuses[]? | select(.name == $c)][0]) as $s
    | [ $p.metadata.name,
        ($p.metadata.labels["pod-template-hash"] // "-"),
        (($s.imageID // "") | capture("(?<d>sha256:[0-9a-f]{64})$").d // "-"),
        (($s.ready // false) | tostring),
        (($s.restartCount // 0) | tostring) ]
    | @tsv' "$TMP/pods.json" > "$TMP/pods.tsv" || return 1
}

# True only on positive evidence: autoscaling off in the values, at least one
# Deployment of the release, and every one of them asking for 0 replicas.
scaled_to_zero() {
  [ "$(jq -r '.autoscaling.enabled == true' "$TMP/values.json")" = false ] || return 1
  kubectl -n "$NS" get deployments -l "app.kubernetes.io/instance=${APP}" -o json > "$TMP/deploys.json" 2>/dev/null || return 1
  jq -e '(.items | length) > 0 and all(.items[]; .spec.replicas == 0)' "$TMP/deploys.json" >/dev/null 2>&1
}

check_pods() {
  if ! list_pods; then
    why="cannot list pods of ${APP} in ${NS}: $(tail -1 "$TMP/kubectl.err" 2>/dev/null)"; state=unknown; return 1
  fi
  n=$(wc -l < "$TMP/pods.tsv" | tr -d ' ')
  if [ "$n" -eq 0 ]; then
    if scaled_to_zero; then
      echo "$revision" > "${OUT}/argo_revision"
      finish idle "Synced and Healthy at ${revision}; scaled to zero on purpose, so no running version to verify"
    fi
    why="no running pods for ${APP} in ${NS}"; state=waiting; return 1
  fi
  hashes=$(cut -f2 "$TMP/pods.tsv" | sort -u | wc -l | tr -d ' ')
  [ "$hashes" -eq 1 ] || { why="${n} pods across ${hashes} ReplicaSets: the rollout has not finished"; state=waiting; return 1; }
  bad=$(awk -F'\t' -v d="$expected" '$3 != d {print $1 " runs " $3}' "$TMP/pods.tsv" | head -3)
  [ -z "$bad" ] || { why="pods do not run ${expected}: $(echo "$bad" | tr '\n' ';')"; state=waiting; return 1; }
  notready=$(awk -F'\t' '$4 != "true" {print $1 " (restarts " $5 ")"}' "$TMP/pods.tsv" | head -3)
  [ -z "$notready" ] || { why="pods not ready: $(echo "$notready" | tr '\n' ';')"; state=waiting; return 1; }
  return 0
}

http_note=""
check_http() {
  http_note=""
  [ -n "$host" ] && [ -n "$ready_path" ] || return 0
  url="https://${host}${ready_path}"
  # No -L: a redirect (an auth wall, a wrong host) is not the service saying
  # it is ready.
  code=$(curl -sS -o /dev/null --connect-timeout 5 --max-time 10 -w '%{http_code}' "$url" 2> "$TMP/curl.err") || true
  case "$code" in
    2??) http_note="${url} answers 2xx"; return 0 ;;
    3??|401|403) http_note="${url} answered HTTP ${code} (auth wall or redirect): HTTP not verified"; return 0 ;;
    000|"") why="${url} did not answer: $(tail -1 "$TMP/curl.err")"; state=waiting; return 1 ;;
    *) why="${url} answered HTTP ${code}"; state=waiting; return 1 ;;
  esac
}

# Restarts are counted from the first pass that saw everything ready; the
# stability window must end with the same pods, still ready, no new restarts.
# Ask Argo CD to look at the repository now rather than at its next poll. A
# refused annotation only costs time: the gate still waits for the revision.
# HG_NO_REFRESH=1 makes the gate read-only (tests, a dry run by hand).
if [ "${HG_NO_REFRESH:-0}" != 1 ]; then
  kubectl -n argocd annotate application "$APP" argocd.argoproj.io/refresh=normal --overwrite >/dev/null 2>&1 \
    || echo "could not request a refresh of ${APP}; waiting for Argo CD's own poll"
fi

deadline=$(( $(date +%s) + TIMEOUT ))
resets=0
stable_since=""
snapshot=""
while :; do
  if resolve_expected && check_argo && check_pods && check_http; then
    now_snapshot=$(cut -f1,3,5 "$TMP/pods.tsv" | sort)
    if [ -z "$stable_since" ] || [ "$now_snapshot" != "$snapshot" ]; then
      if [ -n "$stable_since" ]; then
        resets=$((resets + 1))
        echo "pods changed during the stability window (a restart or a replaced pod); starting it again"
      fi
      stable_since=$(date +%s)
      snapshot=$now_snapshot
    fi
    if [ $(( $(date +%s) - stable_since )) -ge "$STABLE" ]; then
      echo "$revision" > "${OUT}/argo_revision"
      echo "$expected" > "${OUT}/image_digest"
      n=$(wc -l < "$TMP/pods.tsv" | tr -d ' ')
      if [ -n "$http_note" ]; then
        finish healthy "${n} pod(s) on ${expected} at ${revision}, ready for ${STABLE}s with no restarts; ${http_note}"
      fi
      finish healthy "${n} pod(s) on ${expected} at ${revision}, ready for ${STABLE}s with no restarts"
    fi
    why="ready, but not yet for ${STABLE}s without a change"
    [ "$resets" -gt 0 ] && why="${why}; pods restarted or were replaced ${resets} time(s) since they first looked ready"
    state=waiting
  else
    stable_since=""
    snapshot=""
  fi
  echo "waiting: ${why}"
  if [ "$(date +%s)" -ge "$deadline" ]; then
    case "$state" in
      unknown) finish unknown "${why} (after ${TIMEOUT}s)" ;;
      *) finish unhealthy "${why} (after ${TIMEOUT}s)" ;;
    esac
  fi
  sleep "$INTERVAL"
done
