#!/bin/sh
# Usage: values-images.sh <values.yaml>
#
# Prints the value of every `repository:` key in a service values.yaml (or a
# rendered service template), one per line: the images it runs. Used by
# check-image-name.sh (which names another team runs) and tpl-validate-tenant
# (whether deploy-service builds), so both read the field the same way.
#
# A line is read only in the block form every service and template uses,
#   repository: <image>          optionally "quoted" or 'quoted',
#                                optionally followed by a ` # comment`
# where <image> is a plain registry/name reference. Any other line naming a
# repository key (flow style `{repository: x}`, a quoted key, a block scalar
# value, an anchor or alias, an empty value, a comment inside quotes) is not
# guessed at: exit 2.
#
# Block scalars are text and are skipped, whichever way they are opened:
# by a key (`config: |`, `- run: >-`) or by a sequence item (`- |`, the
# form the openclaw values use for shell scripts). As in YAML, a scalar
# holds the lines indented deeper than the key or dash that opened it, and
# blank lines; the first line at that column or shallower ends it. So a
# script or JSON blob mentioning `repository:` neither claims an image nor
# makes the file unreadable.
#
# Exit 0: read (possibly no images). Exit 2: unreadable file, or a
# repository line in a form this does not read. Callers treat 2 as "could
# not decide". check-image-name.sh reads every service's values.yaml, so one
# such line in any service makes every check undecidable until it is fixed;
# CI runs that scan on every pull request and push to main.
#
# POSIX sh plus awk only: alpine/git (busybox) inside Argo, bash on runners.
# yq would parse structurally but is not in alpine/git.
set -u

if [ "$#" -ne 1 ] || [ ! -r "$1" ]; then
  echo "usage: $0 <values.yaml> (readable)" >&2
  exit 2
fi

awk -v scalar=-1 '
  {
    # Inside a block scalar: text, skipped.
    if (scalar >= 0) {
      if ($0 ~ /^[[:space:]]*$/) next
      match($0, /^[[:space:]]*/)
      if (RLENGTH > scalar) next
      scalar = -1
    }
  }
  /^[[:space:]]*#/ { next }
  {
    line = $0
    # A YAML comment starts at a # preceded by whitespace.
    sub(/[[:space:]]+#.*$/, "", line)
    # A block scalar opens at a line ending in | or > (with optional
    # indicators, and an optional anchor or tag before it), as the value of a key
    # or as a sequence item: the dashes then make up the whole line before
    # it, so a plain value merely ending in " - |" opens nothing. It belongs
    # to that key, or to the last dash, and its text is what is indented
    # deeper than that column.
    if (line ~ /:[[:space:]]+([&!][^[:space:]]*[[:space:]]+)*[|>][-+0-9]*[[:space:]]*$/) {
      match(line, /^[[:space:]]*(-[[:space:]]+)*/)
      scalar = RLENGTH
    } else if (line ~ /^[[:space:]]*(-[[:space:]]+)*-[[:space:]]+([&!][^[:space:]]*[[:space:]]+)*[|>][-+0-9]*[[:space:]]*$/) {
      match(line, /^[[:space:]]*(-[[:space:]]+)*/)
      prefix = substr(line, 1, RLENGTH)
      sub(/-[[:space:]]+$/, "", prefix)
      scalar = length(prefix)
    }
  }
  line !~ /(^|[^A-Za-z0-9_-])repository[\047"]?[[:space:]]*:/ { next }
  {
    if (match(line, /^[[:space:]]*repository:[[:space:]]+/)) {
      v = substr(line, RSTART + RLENGTH)
      sub(/[[:space:]]+$/, "", v)
      if (v ~ /^"[^"]*"$/ || v ~ /^\047[^\047]*\047$/) {
        v = substr(v, 2, length(v) - 2)
      }
      if (v ~ /^[A-Za-z0-9][A-Za-z0-9._\/:@-]*$/) {
        print v
        next
      }
    }
    print FILENAME ":" NR ": a repository key in a form this does not read: " $0 > "/dev/stderr"
    bad = 1
  }
  END { exit bad ? 2 : 0 }
' "$1"
