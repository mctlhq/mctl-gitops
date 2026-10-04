#!/bin/sh
# Usage: check-image-name.sh <mctl-gitops checkout> <team> <component_name>
#
# Decides whether <team> may build into and run ghcr.io/mctlhq/<component_name>.
# The rule and the data live in platform-gitops/argo-workflows/config/
# image-names.txt; this script only applies them to the checkout it is given.
#
# Exit 0: allowed. Exit 1: refused. Exit 2: could not decide (bad input, no
# readable list, or a list line it does not understand). Callers treat any
# non-zero exit as a refusal.
#
# POSIX sh plus grep/awk only: it runs in alpine/git (busybox) inside Argo and
# in bash on GitHub runners.
set -u

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <checkout> <team> <component_name>" >&2
  exit 2
fi
ROOT=$1
TEAM=$2
NAME=$3
LIST="$ROOT/platform-gitops/argo-workflows/config/image-names.txt"
SERVICES="$ROOT/platform-gitops/services"

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

# Every non-comment line must be one of the three known forms.
if ! awk '
  /^[[:space:]]*(#|$)/ { next }
  $1 == "grant" && NF == 3 { next }
  ($1 == "reserved" || $1 == "reserved-prefix") && NF == 2 { next }
  { bad = 1; print "unrecognised line " NR ": " $0 > "/dev/stderr" }
  END { exit bad }
' "$LIST"; then
  exit 2
fi

if awk -v t="$TEAM" -v n="$NAME" '
  $1 == "grant" && ($2 == t || $2 == "*") && $3 == n { found = 1 }
  END { exit !found }
' "$LIST"; then
  exit 0
fi

if awk -v n="$NAME" '
  $1 == "reserved" && $2 == n { found = 1 }
  $1 == "reserved-prefix" && index(n, $2) == 1 { found = 1 }
  END { exit !found }
' "$LIST"; then
  echo "image name '${NAME}' is reserved for the platform; team '${TEAM}' may not use it" >&2
  exit 1
fi

for dir in "$SERVICES"/*/"$NAME"; do
  [ -d "$dir" ] || continue
  owner=$(basename "$(dirname "$dir")")
  if [ "$owner" != "$TEAM" ]; then
    echo "image name '${NAME}' belongs to team '${owner}'; team '${TEAM}' may not use it" >&2
    exit 1
  fi
done

# A service may run an image under a name other than its own directory
# (e.g. a preview of another service): those names are taken as well.
for values in "$SERVICES"/*/*/values.yaml; do
  [ -f "$values" ] || continue
  if grep -qE "^[[:space:]]*repository:[[:space:]]*[\"']?ghcr\.io/mctlhq/${NAME}[\"']?[[:space:]]*$" "$values"; then
    owner=$(basename "$(dirname "$(dirname "$values")")")
    if [ "$owner" != "$TEAM" ]; then
      echo "image name '${NAME}' is run by team '${owner}'; team '${TEAM}' may not use it" >&2
      exit 1
    fi
  fi
done

exit 0
