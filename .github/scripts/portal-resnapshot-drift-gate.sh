#!/usr/bin/env bash
# The end state, checked by the same detector that found the problem — but
# scoped in its VERDICT to the server this run touched.
#
# `portal-catalogue-drift.py` is account-wide and takes no server filter, so a
# successfully re-snapshotted `api` would go red because `seerrsense` is stale
# for reasons this run never touched. Worse than noise: the alert names one
# server, so the operator reads "the re-snapshot failed" about a server whose
# re-snapshot worked.
#
# Account-wide drift is `cloudflare-drift.yml`'s job and it runs nightly. This
# gate owns one question — did THIS server end up consistent — and says the
# rest out loud rather than either failing on it or hiding it.
set -euo pipefail
# shellcheck source=.github/scripts/portal-resnapshot-lib.sh
. "$(dirname "$0")/portal-resnapshot-lib.sh"
assert_server_id

# PYTHONUNBUFFERED, because the evidence check reads stdout out of a stream
# merged with stderr. Python block-buffers stdout when it is not a tty and
# line-buffers stderr, so without this the `compared: ...` line can be
# interleaved with a stderr write and lose its line start -- and the anchored
# `^compared: ` then fails to match. That used to cost a spurious green; since
# the gate requires positive evidence it costs the opposite, failing a run
# where the sign-in completed and the catalogue moved. Either way the buffering
# decides the verdict, which is not something a verdict may depend on.
out=$(PYTHONUNBUFFERED=1 python3 scripts/portal-catalogue-drift.py 2>&1) && code=0 || code=$?
printf '%s\n' "$out"

# POSITIVE EVIDENCE FIRST, and it is what makes every branch below safe.
#
# The detector prints `compared: api=76@<last_synced>, ...` for every outcome
# that has one, clean or red. Requiring that line means this gate can only
# reach a verdict about a comparison that HAPPENED.
#
# The alternative was a list of the detector's known failure shapes -- its four
# `[2] ` bail-outs -- with everything else falling through to "consistent".
# That is a list to keep in step with another file, and it answers green for
# every shape not on it: an uncaught exception, a SyntaxError, a missing
# module, an OOM kill. The final gate of a procedure that just took a
# production server down must not report the end state good having compared
# nothing, and only positive evidence rules that out.
# THESE BRANCHES MUST EXIT NON-ZERO, and `${code:-1}` was not that. `:-`
# substitutes only on
# unset-or-empty, and on a clean detector run `code` is the STRING "0" -- so
# both branches below printed their `::error::` and exited 0, passing the step
# and reporting the end state good having compared nothing. Verbatim the
# outcome the paragraph above says positive evidence was chosen to rule out,
# and unreachable today only because of how the detector happens to order its
# own exit codes: the same coupling, moved from a grep into an exit status.
fail() {
  echo "::error::$1"
  [ "${code:-0}" -ne 0 ] && exit "$code"
  exit 1
}

compared=$(printf '%s\n' "$out" | grep -E '^compared: ' || true)
if [ -z "$compared" ]; then
  fail "the catalogue detector produced no \"compared:\" line (exit ${code}): it never compared ${SERVER}, whatever else it printed. Nothing here has been verified."
fi
printf '%s\n' "$compared" | grep -qE "(^|[ ,])${SERVER}=" \
  || fail "the detector compared servers but not ${SERVER}: ${compared}"

if [ "$code" -eq 0 ]; then
  echo "catalogue drift is clean account-wide"
  exit 0
fi

# GLOBAL BAIL-OUTS FIRST. The detector exits 2 before its per-server loop for
# a missing token or a portal it cannot read, and prints no `{server}:` line at
# all -- so a per-server grep finds nothing and the "red for somebody else"
# branch below would report green on a check that made no comparison. That is
# the final gate of this workflow saying the end state is good having measured
# nothing.
#
# The detector marks them itself: every global bail-out starts a line with
# `[2] `, and no per-server message does.
if printf '%s\n' "$out" | grep -qE '^\[2\] '; then
  echo "::error::the catalogue detector could not run (exit ${code}): it never compared ${SERVER}. Fix the detector's own inputs and re-run; nothing here has been verified."
  exit "$code"
fi

# The detector prefixes each finding with the server id it is about
# (`api: mctl_get_lifecycle_ownership is upstream but not ...`). Anchored, so a
# server id appearing inside another server's message does not match.
mine=$(printf '%s\n' "$out" | grep -E "^[[:space:]]*${SERVER}:" || true)
if [ -n "$mine" ]; then
  # THE LINES, not the exit code. `$code` is a MAXIMUM across the account
  # (portal-catalogue-drift.py orders `vanished > failing > undetermined >
  # maintenance` and returns the loudest), so mapping it to a remedy for THIS
  # server inverts exactly what the per-server grep above exists to prevent: a
  # vanished `seerrsense` beside a stale `api` would print "api is missing from
  # the portal entirely" about a server that is present.
  #
  # What is true per server is the finding text, so that is what is quoted and
  # the remedy is left to it.
  echo "::error::catalogue drift names ${SERVER} (account-wide exit ${code}); its own findings follow. Only a line about a MISSING tool means re-snapshot or allowlist-apply; a waiver line is a chore cloudflare-drift.yml separates precisely so nobody is sent through this recipe for it."
  printf '%s\n' "$mine"
  exit "$code"
fi

# Red for somebody else. Surfaced, not swallowed -- and not this run's verdict.
echo "::warning::catalogue drift exit ${code}, but no finding names ${SERVER}: this re-snapshot is consistent and another server is stale. cloudflare-drift.yml owns that."
exit 0
