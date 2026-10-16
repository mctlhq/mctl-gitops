#!/bin/sh
# Usage:
#   check-image-user.sh check [--image-user <user>] <checkout> <team> <component> <image-tag> [<default-repository>]
#   check-image-user.sh fetch-user <image-ref>
#
# check: decides whether a service's image can start under the security
# context the base-service chart will give it. It renders the chart from
# <checkout> with the service's values (platform-gitops/services/<team>/
# <component>/values.yaml; absent on onboard, then <default-repository> names
# the image) and reads the main container's effective runAsNonRoot and
# runAsUser, so a chart default flip or a per-service opt-in is picked up
# without editing this script.
#
# kubelet enforces runAsNonRoot by the uid the container will run as. When the
# security context pins runAsUser, that uid decides. Otherwise it is the
# image's USER, and kubelet can only verify a numeric one: `USER app` makes the
# pod fail with CreateContainerConfigError, and so does root (no USER, `root`,
# or uid 0). Only in that case is the image config read from the registry.
#
# Under runAsNonRoot a failing image is refused. Without it the same finding
# is printed as a warning only: the service runs today, and the warning is
# what tells its owner it will stop once non-root becomes the default.
#
# fetch-user: prints the image config's User (an empty line when the image
# sets none). Credentials come from the dockerconfigjson named by
# $DOCKER_CONFIG_JSON when it has an entry for the registry, otherwise the
# pull is anonymous. A multi-platform image is resolved for $IMAGE_PLATFORM
# (default linux/amd64, the cluster's nodes).
#
# --image-user skips the registry read and uses the given value; tests use it.
#
# Exit 0: allowed (possibly with a warning). Exit 1: refused. Exit 2: could
# not decide (bad input, a render or registry read that failed). A failed
# image read is only fatal when the image's user matters for runAsNonRoot;
# otherwise it is reported as unknown, never as fine.
#
# POSIX sh plus helm, yq (either flavour), jq and curl: alpine/k8s in Argo,
# and the CI runner.
set -u

DOCS="https://docs.mctl.ai/guides/scaffolding#container-requirements"
PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
ACCEPT="application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"

die() { echo "check-image-user: $1" >&2; exit 2; }

TMP=$(mktemp -d) || die "mktemp failed"
trap 'rm -rf "$TMP"' EXIT

# ── Registry ─────────────────────────────────────────────────────────────
# GET <url> into $TMP/body with the current $AUTH header; prints the status.
get() {
  if [ -n "${AUTH:-}" ]; then
    curl -sS -L -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}' \
      -H "Accept: $ACCEPT" -H "Authorization: $AUTH" "$1" || echo 000
  else
    curl -sS -L -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}' \
      -H "Accept: $ACCEPT" "$1" || echo 000
  fi
}

fetch_user() {
  ref=$1
  case "$ref" in
    *[!A-Za-z0-9._:/@-]*|"") die "invalid image reference: $ref" ;;
  esac
  case "$ref" in
    */*) ;;
    *) die "image reference must name a registry: $ref" ;;
  esac
  registry=${ref%%/*}
  case "$registry" in
    *.*|*:*) ;;
    *) die "image reference must name a registry: $ref" ;;
  esac
  api=$registry
  # Docker Hub's API host is not its image-name host.
  [ "$registry" = docker.io ] && api="registry-1.docker.io"
  rest=${ref#*/}
  case "$rest" in
    # The chart writes "<repository>:<tag>", so a digest tag reads as
    # "<repository>:@sha256:...".
    *@*) path=${rest%%@*}; path=${path%:}; reference=${rest#*@} ;;
    *:*) path=${rest%:*}; reference=${rest##*:} ;;
    *) die "image reference has no tag or digest: $ref" ;;
  esac
  [ -n "$path" ] && [ -n "$reference" ] || die "invalid image reference: $ref"
  base="https://${api}/v2/${path}"

  # Token: the registry names its realm in WWW-Authenticate on a 401.
  AUTH=""
  code=$(get "${base}/manifests/${reference}")
  if [ "$code" = 401 ]; then
    challenge=$(tr -d '\r' < "$TMP/headers" | grep -i '^www-authenticate: *bearer' | tail -1)
    realm=$(printf '%s' "$challenge" | sed -n 's/.*realm="\([^"]*\)".*/\1/p')
    service=$(printf '%s' "$challenge" | sed -n 's/.*service="\([^"]*\)".*/\1/p')
    [ -n "$realm" ] || die "${registry} answered 401 without a bearer realm"
    basic=""
    if [ -n "${DOCKER_CONFIG_JSON:-}" ] && [ -r "$DOCKER_CONFIG_JSON" ]; then
      basic=$(jq -r --arg r "$registry" '.auths[$r].auth // empty' "$DOCKER_CONFIG_JSON") \
        || die "cannot parse ${DOCKER_CONFIG_JSON}"
    fi
    if [ -n "$basic" ]; then
      tcode=$(curl -sS -o "$TMP/token" -w '%{http_code}' -G "$realm" \
        --data-urlencode "service=${service}" \
        --data-urlencode "scope=repository:${path}:pull" \
        -H "Authorization: Basic ${basic}" || echo 000)
    else
      tcode=$(curl -sS -o "$TMP/token" -w '%{http_code}' -G "$realm" \
        --data-urlencode "service=${service}" \
        --data-urlencode "scope=repository:${path}:pull" || echo 000)
    fi
    [ "$tcode" = 200 ] || die "token request to ${realm} answered HTTP ${tcode}"
    token=$(jq -r '.token // .access_token // empty' "$TMP/token") || die "unreadable token response"
    [ -n "$token" ] || die "token response from ${realm} carries no token"
    AUTH="Bearer ${token}"
    code=$(get "${base}/manifests/${reference}")
  fi
  [ "$code" = 200 ] || die "manifest ${ref} answered HTTP ${code}"

  media=$(jq -r '.mediaType // empty' "$TMP/body") || die "unreadable manifest for ${ref}"
  if [ -z "$media" ]; then
    # An OCI index or manifest may omit mediaType; the shape tells them apart.
    if jq -e '.manifests' "$TMP/body" >/dev/null 2>&1; then
      media=application/vnd.oci.image.index.v1+json
    fi
  fi
  case "$media" in
    *index*|*manifest.list*)
      os=${PLATFORM%%/*}; arch=${PLATFORM#*/}
      digest=$(jq -r --arg os "$os" --arg arch "$arch" \
        '[.manifests[] | select(.platform.os == $os and .platform.architecture == $arch)][0].digest // empty' \
        "$TMP/body") || die "unreadable index for ${ref}"
      [ -n "$digest" ] || die "${ref} has no ${PLATFORM} image"
      code=$(get "${base}/manifests/${digest}")
      [ "$code" = 200 ] || die "manifest ${digest} answered HTTP ${code}"
      ;;
  esac
  config=$(jq -r '.config.digest // empty' "$TMP/body") || die "unreadable manifest for ${ref}"
  [ -n "$config" ] || die "manifest for ${ref} names no config"
  code=$(get "${base}/blobs/${config}")
  [ "$code" = 200 ] || die "config blob ${config} answered HTTP ${code}"
  jq -e 'has("config")' "$TMP/body" >/dev/null 2>&1 || die "unreadable image config for ${ref}"
  jq -r '.config.User // ""' "$TMP/body"
}

# ── Policy ───────────────────────────────────────────────────────────────
# Classifies an image USER value: root, named, or a non-zero uid.
classify_user() {
  u=${1%%:*}
  case "$u" in
    ""|root) echo root ;;
    *[!0-9]*) echo named ;;
    *) if [ "$u" -eq 0 ]; then echo root; else echo uid; fi ;;
  esac
}

check() {
  IMAGE_USER_SET=false
  IMAGE_USER=""
  if [ "${1:-}" = "--image-user" ]; then
    [ "$#" -ge 2 ] || die "--image-user needs a value"
    IMAGE_USER_SET=true; IMAGE_USER=$2; shift 2
  fi
  [ "$#" -eq 4 ] || [ "$#" -eq 5 ] \
    || die "usage: check [--image-user <user>] <checkout> <team> <component> <image-tag> [<default-repository>]"
  root=$1 team=$2 component=$3 tag=$4 default_repo=${5:-}

  for pair in "team:$team" "component:$component"; do
    value=${pair#*:}
    if [ "$(printf '%s' "$value" | wc -l)" -ne 0 ] \
      || ! printf '%s' "$value" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
      die "invalid ${pair%%:*}: ${value}"
    fi
  done
  case "$tag" in
    *[!A-Za-z0-9._:@-]*|"") die "invalid image tag: ${tag}" ;;
  esac

  chart="$root/platform-gitops/helm-charts/base-service"
  values="$root/platform-gitops/services/${team}/${component}/values.yaml"
  [ -f "$chart/Chart.yaml" ] || die "cannot read ${chart}"

  set -- template chk "$chart" --set-string "image.tag=${tag}"
  if [ -e "$values" ]; then
    [ -r "$values" ] || die "cannot read ${values}"
    set -- "$@" -f "$values"
  else
    [ -n "$default_repo" ] || die "${team}/${component} has no values.yaml and no default repository was given"
    set -- "$@" --set-string "image.repository=${default_repo}"
  fi
  helm "$@" > "$TMP/render.yaml" 2> "$TMP/render.err" || {
    cat "$TMP/render.err" >&2; die "helm template failed for ${team}/${component}"; }

  # Alpine ships two programs named yq (mikefarah's Go one and kislyuk's
  # jq wrapper) and which one an image gets is not pinned, so both are
  # handled. The filter is the same; only the flag that selects JSON differs.
  filter='select(.kind == "Deployment" or .kind == "Rollout") | .spec.template.spec'
  if yq --version 2>&1 | grep -q mikefarah; then
    yq -o json "$filter" "$TMP/render.yaml" > "$TMP/spec.json" 2> "$TMP/yq.err"
  else
    yq -c "$filter" "$TMP/render.yaml" > "$TMP/spec.json" 2> "$TMP/yq.err"
  fi || { cat "$TMP/yq.err" >&2; die "cannot parse the render"; }
  # Exactly one workload: the chart renders a Deployment or a Rollout.
  n=$(jq -s 'length' "$TMP/spec.json") || die "cannot parse the render"
  [ "$n" = 1 ] || die "expected one Deployment or Rollout in the render, found ${n}"

  # The container's own setting wins over the pod's, including an explicit
  # false, so a key's presence is tested rather than its truthiness.
  eff='def eff($k): (.containers[0].securityContext // {}) as $c | (.securityContext // {}) as $p
        | if ($c | has($k)) then $c[$k] elif ($p | has($k)) then $p[$k] else null end;'
  nonroot=$(jq -r "$eff"' eff("runAsNonRoot") == true' "$TMP/spec.json") || die "cannot read the pod spec"
  sc_uid=$(jq -r "$eff"' eff("runAsUser") // "" | tostring' "$TMP/spec.json") || die "cannot read the pod spec"
  image=$(jq -r '.containers[0].image // ""' "$TMP/spec.json") || die "cannot read the pod spec"

  if [ "$nonroot" = true ]; then mode="runAsNonRoot"; else mode="no runAsNonRoot yet"; fi

  if [ -n "$sc_uid" ]; then
    case "$sc_uid" in
      *[!0-9]*) die "runAsUser is not a number: ${sc_uid}" ;;
    esac
    if [ "$sc_uid" -ne 0 ]; then
      echo "OK: ${team}/${component} runs as uid ${sc_uid} from its security context (${mode})"
      return 0
    fi
    if [ "$nonroot" = true ]; then
      echo "REFUSED: ${team}/${component} sets runAsUser 0 together with runAsNonRoot; the pod cannot start" >&2
      return 1
    fi
    echo "WARNING: ${team}/${component} sets runAsUser 0; it will not start once non-root becomes the default. See ${DOCS}"
    return 0
  fi

  if [ "$IMAGE_USER_SET" = false ]; then
    if ! IMAGE_USER=$(fetch_user "$image"); then
      if [ "$nonroot" = true ]; then
        echo "REFUSED: could not read the image user of ${image}, and ${team}/${component} runs with runAsNonRoot" >&2
        return 2
      fi
      echo "UNKNOWN: could not read the image user of ${image}; not checked (${mode})"
      return 0
    fi
  fi

  kind=$(classify_user "$IMAGE_USER")
  case "$kind" in
    uid)
      echo "OK: ${image} runs as USER ${IMAGE_USER} (${mode})"
      return 0
      ;;
    named) why="a user name (USER ${IMAGE_USER}); Kubernetes can only verify a numeric uid" ;;
    root) why="root (USER ${IMAGE_USER:-not set})" ;;
  esac
  if [ "$nonroot" = true ]; then
    echo "REFUSED: ${image} runs as ${why}, and ${team}/${component} runs with runAsNonRoot, so the pod cannot start. Set a numeric non-root USER, e.g. USER 10001:10001. See ${DOCS}" >&2
    return 1
  fi
  echo "WARNING: ${image} runs as ${why}. It deploys today, but will not start once non-root becomes the default. Set a numeric non-root USER, e.g. USER 10001:10001. See ${DOCS}"
  return 0
}

[ "$#" -ge 1 ] || die "usage: $0 check|fetch-user ..."
cmd=$1; shift
case "$cmd" in
  check) check "$@" ;;
  fetch-user) [ "$#" -eq 1 ] || die "usage: fetch-user <image-ref>"; fetch_user "$1" ;;
  *) die "unknown command: ${cmd}" ;;
esac
