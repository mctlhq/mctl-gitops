#!/usr/bin/env bash
# Print the labels of the pull request a merge_group run is testing, as a JSON
# array, for gates whose escape hatch is a pull request label
# (mctlhq/.github#351). A merge_group payload carries no labels, so they are
# read from the API and bound to the queued commit before they are trusted.
#
# Inputs (environment):
#   HEAD_REF  github.event.merge_group.head_ref,
#             refs/heads/gh-readonly-queue/<base>/pr-<N>-<pr head sha>
#   BASE_SHA  github.event.merge_group.base_sha
#   REPO      owner/name
#   GH_TOKEN  token with pull-requests: read
# The current checkout must be the merge group head (HEAD).
#
# Fails closed: any read that fails, or any answer that does not tie the labels
# to exactly this queued commit, exits non-zero and prints nothing, so the
# caller's gate fails instead of treating "could not read" as "no labels".
# A group holding more than one pull request prints [] on purpose: one pull
# request's label must not excuse a change another pull request in the same
# group made.
set -euo pipefail

: "${HEAD_REF:?}" "${BASE_SHA:?}" "${REPO:?}"

re='^refs/heads/gh-readonly-queue/.+/pr-([0-9]+)-([0-9a-f]{40})$'
[[ "$HEAD_REF" =~ $re ]] || { echo "merge group ref '$HEAD_REF' does not name one pull request" >&2; exit 1; }
pr="${BASH_REMATCH[1]}"
pr_head="${BASH_REMATCH[2]}"

# Plain assignments: set -e does not see a failure inside a command
# substitution used as an argument.
count=$(git rev-list --first-parent --count "$BASE_SHA..HEAD")
if [ "$count" != "1" ]; then
  echo "merge group holds $count commits on top of $BASE_SHA; labels of pull request $pr are not applied to the group" >&2
  echo '[]'
  exit 0
fi

# The queued commit must be base + exactly this pull request's head.
parents=$(git rev-list --parents -n 1 HEAD)
read -r _ p1 p2 extra <<< "$parents"
[ "$p1" = "$BASE_SHA" ] && [ "${p2:-}" = "$pr_head" ] && [ -z "${extra:-}" ] || {
  echo "merge group head is not a merge of $BASE_SHA and $pr_head (parents: ${p1:-} ${p2:-} ${extra:-})" >&2
  exit 1
}

body=$(gh api "repos/$REPO/pulls/$pr")
labels=$(jq -ce --arg sha "$pr_head" '
  if .head.sha == $sha
  then [.labels[].name | strings]
  else error("pull request head \(.head.sha) is not the queued \($sha)") end' <<< "$body")
printf '%s\n' "$labels"
