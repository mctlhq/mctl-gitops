#!/usr/bin/env bash
# Decide whether a release-window/* (or, for a removal, release-window-removal/*)
# pull request may enter the merge queue, and wait until it may. Run by the
# enqueue-window job of release-window-pr.yml and release-window-removal-pr.yml
# from a checkout of main, with a READ-ONLY token in GH_TOKEN; that job enqueues with
# the mctl-gitops-pr App token only after this script has said ready=true.
#
#     REPO=o/r PR=N EXPECT_HEAD=<sha> TARGET=<template path> [WINDOW_KIND=add|remove] \
#       GITHUB_OUTPUT=... RUNNER_TEMP=... bash scripts/release-window-enqueue-wait.sh
#
# The owner's MFA approval on the release-window decide page is the only human
# review of a window (docs/plans/sync-window-write-path.md, section 5, item 6).
# This is the machine side of it: it enqueues the one pull request the approved
# dispatch produced, and refuses everything else. auto-merge.yml keeps
# refusing these paths; only this job, running code from main, may enqueue.
#
# Guards, all judged on ONE head (head_sha, read once at the start):
#   * head_sha is EXPECT_HEAD, the commit the opening job pushed after it had
#     re-rendered the approved window and checked the edit changed nothing else;
#   * the PR is from the App (mctl-gitops-pr[bot]), its head is in this
#     repository and on a release-window/ branch (WINDOW_KIND=add, the default)
#     or a release-window-removal/ branch (WINDOW_KIND=remove). Nothing else is
#     a kind: an addition is refused under remove and a removal under add;
#   * for a removal the diff only deletes: no added line and at least one
#     deleted one (a removal that adds text is not a removal);
#   * the full file list is read and is exactly TARGET, one of the two project
#     templates (apps or platform, never default), with no rename;
#   * the head has not moved, reviewDecision is APPROVED and an approving review
#     was given on exactly head_sha;
#   * every check run of head_sha completed green and the required checks
#     reported (scripts/release-bump-checks-ready.py).
#
# Exit 0 with ready=true: enqueue head_sha (pr_id is the PR node id).
# Exit 0 with ready=false: the PR is already merged or closed; nothing to do.
# Anything else exits non-zero: a guard refused, a read failed, the head moved,
#   changes were requested, a check failed, or the wait timed out. A read that
#   fails is never "nothing wrong". A refusal leaves the pull request open and
#   the window off.
set -euo pipefail

: "${REPO:?REPO is required}" "${PR:?PR is required}" "${EXPECT_HEAD:?EXPECT_HEAD is required}" "${TARGET:?TARGET is required}" "${GITHUB_OUTPUT:?}" "${RUNNER_TEMP:?}"
WAIT_SECONDS=${WAIT_SECONDS:-2700}
# enqueue: wait for the approval and every check. dispatch: stop at the approval
# and say whether the formal review still has to be requested.
STAGE=${STAGE:-enqueue}
WINDOW_KIND=${WINDOW_KIND:-add}
APP_LOGIN='mctl-gitops-pr[bot]'
# The required status checks of ruleset main-protection (id 18465404). Keep in
# step with the ruleset and with release-bump-enqueue-wait.sh.
# The dispatch-formal-review job of the same workflow requests that review: it
# runs this script with STAGE=dispatch (#3047).
REQUIRED_CHECKS=agy-formal-review,cloudflare-plan,reserved-hosts,validate
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

die() { echo "::error::$*"; exit 1; }
case "$WINDOW_KIND" in
  add) BRANCH_PREFIX='release-window/' ;;
  remove) BRANCH_PREFIX='release-window-removal/' ;;
  *) die "WINDOW_KIND must be add or remove (got '${WINDOW_KIND}'); not enqueueing." ;;
esac
not_ready() { echo "::notice::$*"; echo "ready=false" >> "$GITHUB_OUTPUT"; exit 0; }

case "$STAGE" in enqueue|dispatch) ;; *) die "STAGE must be enqueue or dispatch (got '${STAGE}')." ;; esac
[[ "$PR" =~ ^[0-9]+$ ]] || die "no pull request number (got '${PR}'); not enqueueing."
[[ "$EXPECT_HEAD" =~ ^[0-9a-f]{40}$ ]] || die "no pushed head sha (got '${EXPECT_HEAD}'); not enqueueing."
[[ "$TARGET" =~ ^platform-gitops/bootstrap/templates/projects/project-(apps|platform)\.yaml$ ]] \
  || die "'${TARGET}' is not the apps or platform project template; not enqueueing."

# --- One read of the PR; every later check is pinned to this head. ---------
if ! info=$(gh api "repos/${REPO}/pulls/${PR}" \
      --jq '[.head.sha, .changed_files, .user.login, (.head.repo.full_name // ""), .head.ref, .state, .merged, .node_id, .additions, .deletions] | map(tostring) | join("\u001f")'); then
  die "could not read #${PR}; not enqueueing."
fi
# Unit separator, not tab: see release-bump-enqueue-wait.sh.
IFS=$'\x1f' read -r head_sha expected author head_repo head_ref state merged pr_id additions deletions <<<"$info"
[[ "$head_sha" =~ ^[0-9a-f]{40}$ ]] || die "#${PR} has no readable head sha; not enqueueing."
[[ -n "$pr_id" ]] || die "#${PR} has no node id; not enqueueing."
if [ "$merged" = true ]; then not_ready "#${PR} is already merged."; fi
if [ "$state" = closed ]; then not_ready "#${PR} is closed."; fi
[ "$state" = open ] || die "#${PR} is in state '${state}'; not enqueueing."
[ "$head_sha" = "$EXPECT_HEAD" ] || die "the head of #${PR} is ${head_sha}, not the commit this run pushed (${EXPECT_HEAD}); not enqueueing."
[ "$author" = "$APP_LOGIN" ] || die "#${PR} is authored by ${author}, not ${APP_LOGIN}; it needs a human merge."
[ "$head_repo" = "$REPO" ] || die "the head of #${PR} is in '${head_repo}', not ${REPO}; it needs a human merge."
case "$head_ref" in "${BRANCH_PREFIX}"?*) ;; *) die "#${PR} is on '${head_ref}', not a ${BRANCH_PREFIX} branch." ;; esac
if [ "$WINDOW_KIND" = remove ]; then
  [ "$additions" = 0 ] && [ "$deletions" -ge 1 ] || die "#${PR} is not a pure deletion (${additions} added, ${deletions} deleted lines, or the counts are unreadable); not enqueueing."
fi

# --- The file list, read in full: exactly the one project template. ----------
if ! files=$(gh api --paginate "repos/${REPO}/pulls/${PR}/files?per_page=100" \
      --jq '.[] | [.filename, (.previous_filename // "")] | @tsv'); then
  die "could not list the files of #${PR}; not enqueueing."
fi
[ "$expected" = 1 ] || die "#${PR} reports ${expected} changed files, not one; not enqueueing."
[ "$files" = "${TARGET}"$'\t' ] || die "#${PR} does not change exactly ${TARGET} (and nothing renamed); not enqueueing."

# --- Wait for the approval on head_sha and for green checks. ---------------
deadline=$((SECONDS + WAIT_SECONDS))
hinted=0
while :; do
  # GraphQL variables and jq bindings, not shell expansions.
  # shellcheck disable=SC2016
  if ! view=$(gh api graphql \
        -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){headRefOid state reviewDecision reviews(states:APPROVED,last:100){nodes{commit{oid}}}}}}' \
        -f o="${REPO%%/*}" -f r="${REPO##*/}" -F n="$PR" \
        --jq '.data.repository.pullRequest | .headRefOid as $h | "\($h) \(.state) \(.reviewDecision) \([.reviews.nodes[] | select(.commit.oid == $h)] | length)"'); then
    die "could not read the review state of #${PR}; not enqueueing."
  fi
  read -r cur state decision on_head <<<"$view"
  [ "$cur" = "$head_sha" ] || die "#${PR} head moved from ${head_sha} to ${cur}; the judged head is gone, not enqueueing."
  case "$state" in
    MERGED) not_ready "#${PR} merged." ;;
    CLOSED) not_ready "#${PR} was closed." ;;
    OPEN) ;;
    *) die "#${PR} is in state '${state}'; not enqueueing." ;;
  esac
  approved=0
  case "$decision" in
    APPROVED) [[ "$on_head" =~ ^[1-9][0-9]*$ ]] && approved=1 ;;
    REVIEW_REQUIRED|null) ;;
    CHANGES_REQUESTED) die "changes were requested on #${PR}; not enqueueing." ;;
    *) die "unknown review decision '${decision}' on #${PR}; not enqueueing." ;;
  esac
  if [ "$approved" = 1 ]; then
    if ! total=$(gh api "repos/${REPO}/commits/${head_sha}/check-runs?per_page=1" --jq .total_count) \
       || ! runs=$(gh api --paginate "repos/${REPO}/commits/${head_sha}/check-runs?per_page=100" \
            --jq '.check_runs[] | {id, name, status, conclusion}'); then
      die "could not read the check runs of ${head_sha}; not enqueueing."
    fi
    if [ "$STAGE" = dispatch ]; then
      [ "$(jq -s length <<<"$runs")" = "$total" ] \
        || die "the check runs of ${head_sha} were not read in full; not dispatching."
      formal=$(jq -rs '[.[] | select(.name == "agy-formal-review")] | sort_by(.id) | last
        | if . == null then "absent" else "\(.status) \(.conclusion)" end' <<<"$runs") \
        || die "could not evaluate the check runs of ${head_sha}; not dispatching."
      case "$formal" in
        absent|"completed "*) ;;
        *) echo "::notice::agy-formal-review on ${head_sha} is already running (${formal})."
           echo "dispatch=false" >> "$GITHUB_OUTPUT"; exit 0 ;;
      esac
      if [ "$formal" = "completed success" ]; then
        echo "::notice::agy-formal-review already passed on ${head_sha}."
        echo "dispatch=false" >> "$GITHUB_OUTPUT"; exit 0
      fi
      { echo "dispatch=true"; echo "head_sha=${head_sha}"; } >> "$GITHUB_OUTPUT"
      echo "::notice::#${PR} is approved on ${head_sha}; requesting the formal review (now: ${formal})."
      exit 0
    fi
    # No check run of the enqueueing job lives on the PR head (it runs in the
    # release workflow on main), so nothing is excluded: an empty --own-check
    # matches no run, because a run without a name is already "unknown".
    rc=0
    verdict=$(python3 "$root/scripts/release-bump-checks-ready.py" --own-check "" \
      --expect "$total" --required "$REQUIRED_CHECKS" <<<"$runs") || rc=$?
    case "$rc" in
      0)
        {
          echo "ready=true"
          echo "head_sha=${head_sha}"
          echo "pr_id=${pr_id}"
        } >> "$GITHUB_OUTPUT"
        echo "::notice::#${PR} is approved on ${head_sha} and its checks are green."
        exit 0 ;;
      10)
        echo "waiting for checks: ${verdict}"
        if [ "$hinted" = 0 ] && [[ "$verdict" == *"agy-formal-review: not reported"* ]]; then
          echo "::notice::no agy-formal-review on ${head_sha} yet; the dispatch-formal-review job requests it. If that job failed, run: gh workflow run agy-formal-dispatch.yml --repo mctlhq/.github --ref main -f repository=${REPO} -f pr_number=${PR} -f head_sha=${head_sha}"
          hinted=1
        fi ;;
      *) die "#${PR} is not mergeable: ${verdict}" ;;
    esac
  else
    echo "waiting for an approval on ${head_sha} (review decision ${decision})"
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    die "#${PR} was not approved and green within $((WAIT_SECONDS / 60)) minutes; not enqueueing. Once it is approved and green, re-run only the failed enqueue-window job (never open-pr: it refuses the existing branch), or enqueue by hand with tools/merge-gitops-pr.sh ${PR}."
  fi
  sleep 30
done
