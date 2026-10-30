#!/bin/sh
# Usage: check-image-name.sh [--tenant] [--build] <checkout> <registry> <team> <component_name>
#
# Decides whether <team> may run (and, with --build, build into)
# <registry>/<component_name>. The rule and the data live in
# platform-gitops/argo-workflows/config/image-names.txt; this script only
# applies them to the checkout it is given.
#
#   --tenant  the caller is a tenant workflow (Argo), where <team> is a value
#             the requester supplied: it must be an existing tenant
#             (platform-gitops/tenants/<team>/), and never "platform".
#   --build   the caller is about to push to the name, not only run it.
#   <registry> the registry prefix the caller pushes to or pulls from; it
#             must equal the list's `registry` line, so a caller deriving a
#             different organisation is refused rather than checked against
#             names it does not use.
#
# Exit 0: allowed. Exit 1: refused. Exit 2: could not decide (bad input, no
# readable list, or a list line it does not understand). Callers treat any
# non-zero exit as a refusal.
#
# POSIX sh plus grep/awk only: it runs in alpine/git (busybox) inside Argo and
# in bash on GitHub runners.
set -u

TENANT=false
BUILD=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --tenant) TENANT=true; shift ;;
    --build) BUILD=true; shift ;;
    --*) echo "unknown option: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
if [ "$#" -ne 4 ]; then
  echo "usage: $0 [--tenant] [--build] <checkout> <registry> <team> <component_name>" >&2
  exit 2
fi
ROOT=$1
REGISTRY=$2
TEAM=$3
NAME=$4
LIST="$ROOT/platform-gitops/argo-workflows/config/image-names.txt"
SERVICES="$ROOT/platform-gitops/services"
TENANTS="$ROOT/platform-gitops/tenants"

for pair in "team:$TEAM" "component_name:$NAME"; do
  value=${pair#*:}
  # A newline would let grep match one good line of a multi-line value.
  if [ "$(printf '%s' "$value" | wc -l)" -ne 0 ] \
    || ! printf '%s' "$value" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
    echo "invalid ${pair%%:*}: ${value}" >&2
    exit 2
  fi
done

if [ ! -r "$LIST" ] || [ ! -d "$SERVICES" ]; then
  echo "cannot read ${LIST} or ${SERVICES}" >&2
  exit 2
fi
# Without the tenants tree every team would read as "not a tenant".
if [ "$TENANT" = true ] && [ ! -d "$TENANTS" ]; then
  echo "cannot read ${TENANTS}" >&2
  exit 2
fi

# Every non-comment line must be one of the known forms, and there must be
# exactly one registry line.
if ! awk '
  /^[[:space:]]*(#|$)/ { next }
  $1 == "grant" && NF == 3 && $2 != "*" { next }
  ($1 == "reserved" || $1 == "reserved-prefix" || $1 == "shared") && NF == 2 { next }
  $1 == "registry" && NF == 2 { registries++; next }
  { bad = 1; print "unrecognised line " NR ": " $0 > "/dev/stderr" }
  END {
    if (registries != 1) { bad = 1; print "need exactly one registry line" > "/dev/stderr" }
    exit bad
  }
' "$LIST"; then
  exit 2
fi

LIST_REGISTRY=$(awk '$1 == "registry" { print $2 }' "$LIST")
if [ "$REGISTRY" != "$LIST_REGISTRY" ]; then
  echo "registry '${REGISTRY}' is not the one image-names.txt governs ('${LIST_REGISTRY}')" >&2
  exit 2
fi

if [ "$TENANT" = true ]; then
  # The grants to team "platform" are for builds dispatched by hand; a tenant
  # workflow can never act as that team, nor as one that does not exist.
  if [ "$TEAM" = platform ] || [ ! -d "$TENANTS/$TEAM" ]; then
    echo "team '${TEAM}' is not an existing tenant" >&2
    exit 1
  fi
fi

has() { # has <keyword> [<field2>] -- is there a line "<keyword> <NAME>" (or "<keyword> <field2> <NAME>")
  awk -v k="$1" -v t="${2-}" -v n="$NAME" '
    $1 == k && NF == 2 && t == "" && $2 == n { found = 1 }
    $1 == k && NF == 3 && t != "" && $2 == t && $3 == n { found = 1 }
    END { exit !found }
  ' "$LIST"
}

# 1. An explicit grant to this team.
if has grant "$TEAM"; then
  exit 0
fi

# 2. Reserved for the platform.
if has reserved || awk -v n="$NAME" '
  $1 == "reserved-prefix" && index(n, $2) == 1 { found = 1 }
  END { exit !found }
' "$LIST"; then
  echo "image name '${NAME}' is reserved for the platform; team '${TEAM}' may not use it" >&2
  exit 1
fi

# 3. A shared name: several teams may hold a service by that name, but only a
#    granted team may push to the image.
if has shared; then
  if [ "$BUILD" = true ]; then
    echo "image name '${NAME}' is shared; only a granted team may build it, not '${TEAM}'" >&2
    exit 1
  fi
  exit 0
fi

# 4. A name another team already has.
for dir in "$SERVICES"/*/"$NAME"; do
  [ -d "$dir" ] || continue
  owner=$(basename "$(dirname "$dir")")
  if [ "$owner" != "$TEAM" ]; then
    echo "image name '${NAME}' belongs to team '${owner}'; team '${TEAM}' may not use it" >&2
    exit 1
  fi
done

# A service may run an image under a name other than its own directory
# (e.g. a preview of another service): those names are taken as well. The
# images are read by values-images.sh, the same reader tpl-validate-tenant
# uses; a values.yaml it cannot read means this cannot decide.
VALUES_IMAGES="$ROOT/platform-gitops/argo-workflows/scripts/values-images.sh"
if [ ! -r "$VALUES_IMAGES" ]; then
  echo "cannot read ${VALUES_IMAGES}" >&2
  exit 2
fi
for values in "$SERVICES"/*/*/values.yaml; do
  [ -f "$values" ] || continue
  if ! images=$(sh "$VALUES_IMAGES" "$values"); then
    exit 2
  fi
  if printf '%s\n' "$images" | grep -qxF "${REGISTRY}/${NAME}"; then
    owner=$(basename "$(dirname "$(dirname "$values")")")
    if [ "$owner" != "$TEAM" ]; then
      echo "image name '${NAME}' is run by team '${owner}'; team '${TEAM}' may not use it" >&2
      exit 1
    fi
  fi
done

exit 0
