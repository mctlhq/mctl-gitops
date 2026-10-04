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
# guessed at: exit 2. So is a line that looks like one but may sit inside
# another key's block scalar (`config: |`), where it is text, not a key:
# reading it as an image would decide ownership and builds from a string.
#
# Exit 0: read (possibly no images). Exit 2: unreadable file, or a
# repository line in a form this does not read. Callers treat 2 as "could
# not decide".
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
    # Inside a block scalar: every line indented deeper than the key that
    # opened it, and blank lines. That is text, skipped, except a line that
    # would be a repository key were it not text: the region is measured
    # counting a leading "- " too, so it can only be too wide, and a key
    # it swallowed by mistake must refuse rather than vanish. Text merely
    # mentioning repository (JSON in a config block) is skipped.
    if (scalar >= 0) {
      if ($0 ~ /^[[:space:]]*$/) next
      match($0, /^[[:space:]-]*/)
      if (RLENGTH > scalar) {
        if ($0 ~ /^[[:space:]-]*[\047"]?repository[\047"]?[[:space:]]*:/) {
          print FILENAME ":" NR ": a repository key inside a block scalar: " $0 > "/dev/stderr"
          bad = 1
        }
        next
      }
      scalar = -1
    }
  }
  /^[[:space:]]*#/ { next }
  {
    line = $0
    # A YAML comment starts at a # preceded by whitespace.
    sub(/[[:space:]]+#.*$/, "", line)
    if (line ~ /:[[:space:]]+[|>][-+0-9]*[[:space:]]*$/) {
      match(line, /^[[:space:]]*/)
      scalar = RLENGTH
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
