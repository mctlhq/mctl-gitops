#!/usr/bin/env bash
# Prints the roots listed in infrastructure/cloudflare/.local-state-roots, one
# per line, normalised.
#
# Three workflow steps read that file — drift discovery, the coverage guard and
# the plan job's backend assertion — and all three compare its lines against
# paths produced by find or by the job matrix. An entry that fails to match is
# not an error anywhere: it simply excepts nothing, which in drift's case means
# the nightly false alarm this list exists to stop carries on. So the parsing
# lives in one place and the callers validate the result.
#
# Normalised means: CR stripped (a file saved with CRLF would otherwise carry \r
# into every pattern), inline comments removed, surrounding whitespace trimmed,
# and a leading "infrastructure/cloudflare/" added if the entry omits it — the
# prose in the file and the README both name roots the short way, so both forms
# have to mean the same thing.
set -euo pipefail

file="${1:-infrastructure/cloudflare/.local-state-roots}"
[ -f "$file" ] || exit 0

# awk 'NF' rather than grep -v '^$': an empty result is the normal end state of
# this list — the last root finishes its migration, its line goes, the comments
# stay — and grep exits 1 when it prints nothing, which under the callers' `set
# -euo pipefail` would fail every workflow that reads the list. awk exits 0
# whether or not it printed anything.
tr -d '\r' < "$file" \
  | sed -e 's/#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
  | awk 'NF' \
  | sed -e 's#^infrastructure/cloudflare/##' -e 's#^#infrastructure/cloudflare/#' \
  | sort -u
