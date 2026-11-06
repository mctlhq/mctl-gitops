#!/bin/sh
# Usage, from the root of a mctl-gitops checkout:
#   release-gate-guard.sh target <team> <service>   before anything is written
#   release-gate-guard.sh outgoing <base-ref>       before every push attempt
#
# A values file in a gated group (platform-gitops/release-gates.yaml) moves only
# with its whole group, through the bump workflows or a reviewed PR. The shared
# workflow templates change one service at a time, so they refuse a gated
# service outright, whoever started the workflow.
#
# `target` asks whether this service may be changed at all. `outgoing` looks at
# what the push would actually send, read again after each rebase, because the
# gate on main may have changed while this run was working.
#
# Exit 0: not gated. Exit 6: refused. Anything this script cannot read or cannot
# decide is a refusal, for every service: not knowing the group is not knowing
# that a service is outside it. A caller must treat every non-zero exit, a
# missing script included, as a refusal.
#
# Portable sh and yq v4, which every image running this has. mctl-workflow-tools
# has no python. A yq that is missing or answers anything unexpected refuses.
set -u
# Paths from the gate file are split unquoted; a `*` must stay a `*` and refuse.
set -f

GATE_FILE=platform-gitops/release-gates.yaml
GUARD_FILE=platform-gitops/argo-workflows/scripts/release-gate-guard.sh

refuse() {
  printf '%s\n' "ERROR: release gate: $1" >&2
  exit 6
}

# Strict on purpose: a token that looks like a path but has another shape cannot
# be compared reliably, so it refuses rather than being skipped.
valid_gated_path() {
  case "$1" in
    platform-gitops/services/*/*/values.yaml) ;;
    *) return 1 ;;
  esac
  _rest=${1#platform-gitops/services/}
  _team=${_rest%%/*}
  _rest=${_rest#*/}
  _svc=${_rest%%/*}
  [ "$_rest" = "$_svc/values.yaml" ] && valid_name "$_team" && valid_name "$_svc"
}

valid_name() {
  case "$1" in
    '' | -* | *[!a-z0-9-]*) return 1 ;;
  esac
  [ "${#1}" -le 63 ]
}

# The same fields scripts/release-gate.py reads, through a real YAML parser, so
# notes, comments and other keys in the file mean nothing here.
load_gated() {
  [ ! -L "$GATE_FILE" ] || refuse "$GATE_FILE is a symlink"
  [ -f "$GATE_FILE" ] && [ -r "$GATE_FILE" ] || refuse "$GATE_FILE cannot be read"
  _shape=$(yq eval '.gates | tag' "$GATE_FILE" 2>/dev/null) || refuse "$GATE_FILE cannot be parsed"
  [ "$_shape" = '!!seq' ] || refuse "$GATE_FILE has no list of gates"
  # A gate with no list of paths guards nothing, and a non-string entry cannot be
  # compared: either means the file is not what this script understands.
  _bad=$(yq eval '[.gates[] | select((.paths | tag) != "!!seq" or (.paths | length) == 0)] | length' "$GATE_FILE" 2>/dev/null) ||
    refuse "$GATE_FILE cannot be parsed"
  [ "$_bad" = 0 ] || refuse "$GATE_FILE has a gate with no paths"
  _bad=$(yq eval '[.gates[] | (.paths[], (.prepull_paths // [])[]) | select(tag != "!!str")] | length' "$GATE_FILE" 2>/dev/null) ||
    refuse "$GATE_FILE cannot be parsed"
  [ "$_bad" = 0 ] || refuse "$GATE_FILE lists something that is not a string"
  _paths=$(yq eval '.gates[] | (.paths[], (.prepull_paths // [])[])' "$GATE_FILE" 2>/dev/null) ||
    refuse "$GATE_FILE cannot be parsed"
  GATED=""
  for _t in $_paths; do
    valid_gated_path "$_t" || refuse "$GATE_FILE names a path of unknown shape: $_t"
    GATED="$GATED $_t"
  done
  [ -n "$GATED" ] || refuse "$GATE_FILE names no values file"
}

check_target() {
  _team=${1-}
  _service=${2-}
  valid_name "$_team" || refuse "invalid team name: '$_team'"
  valid_name "$_service" || refuse "invalid service name: '$_service'"
  _dir="platform-gitops/services/$_team/$_service"
  for _p in platform-gitops platform-gitops/services "platform-gitops/services/$_team" \
    "$_dir" "$_dir/values.yaml"; do
    [ ! -L "$_p" ] || refuse "$_p is a symlink, cannot tell which service it names"
  done
  for _g in $GATED; do
    _gdir=${_g%/values.yaml}
    if [ "$_gdir" = "$_dir" ] || [ "$_gdir" -ef "$_dir" ] || [ "$_g" -ef "$_dir/values.yaml" ]; then
      refuse "$_team/$_service belongs to a release-gated group; move it with the whole group, through a reviewed PR or the release workflow"
    fi
  done
}

check_outgoing() {
  _base=${1-}
  [ -n "$_base" ] || refuse "no base ref to compare the push against"
  git rev-parse --verify --quiet "$_base^{commit}" >/dev/null ||
    refuse "cannot read base ref $_base"
  git rev-parse --verify --quiet 'HEAD^{commit}' >/dev/null || refuse "cannot read HEAD"
  _names=$(git -c core.quotepath=off log --format= --name-only --no-renames -m "$_base..HEAD") ||
    refuse "cannot list what this push would send"
  while IFS= read -r _name; do
    [ -n "$_name" ] || continue
    case "$_name" in
      \"*) refuse "cannot read a changed path unambiguously: $_name" ;;
    esac
    case "$_name" in
      "$GATE_FILE" | "$GUARD_FILE") refuse "this push would change $_name" ;;
    esac
    for _g in $GATED; do
      case "$_name" in
        "${_g%/values.yaml}"/*)
          refuse "this push would change $_name, which belongs to a release-gated group; move it with the whole group, through a reviewed PR or the release workflow"
          ;;
      esac
    done
  done <<EOF
$_names
EOF
}

load_gated
case "${1-}" in
  target)
    [ "$#" -eq 3 ] || refuse "usage: target <team> <service>"
    check_target "$2" "$3"
    ;;
  outgoing)
    [ "$#" -eq 2 ] || refuse "usage: outgoing <base-ref>"
    check_outgoing "$2"
    ;;
  *)
    refuse "unknown mode: '${1-}'"
    ;;
esac
exit 0
