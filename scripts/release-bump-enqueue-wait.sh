#!/usr/bin/env bash
# Decide whether a release-bump/* pull request may enter the merge queue, and
# wait until it may. Run by the enqueue-bump job of release-deploy.yaml and
# gitops-bump.yaml from a checkout of main, with a READ-ONLY token in GH_TOKEN;
# that job enqueues with the mctl-gitops-pr App token only after this script has
# said ready=true.
#
#     REPO=o/r PR=N GITHUB_OUTPUT=... RUNNER_TEMP=... bash scripts/release-bump-enqueue-wait.sh
#
# Why this is not in auto-merge.yml any more: events caused by GITHUB_TOKEN do
# not start workflow runs, and that includes the merge_group event of a queue
# entry that GITHUB_TOKEN created. A bump enqueued from auto-merge.yml sat in
# AWAITING_CHECKS with no validate/reserved-hosts/cloudflare-plan run until a
# person re-enqueued it (mctl-api 4.167.0 #2780, 4.168.0 #2792). The App token
# that can enqueue so that the checks do start may only be released to a job
# that runs code from main, which auto-merge.yml (pull_request_review, merge-ref
# code) is not.
#
# Guards, all judged on ONE head (head_sha, read once at the start):
#   * the PR is from the App (mctl-gitops-pr[bot]), its head is in this
#     repository and on a release-bump/ branch;
#   * the full file list is read and none of it is an auto-merge protected
#     path (the protected_re of auto-merge.yml, read from this checkout of main);
#   * the diff main...head_sha passes scripts/release-bump-diff-guard.py;
#   * the head has not moved, reviewDecision is APPROVED and an approving review
#     was given on exactly head_sha;
#   * every check run of head_sha completed green and the required checks
#     reported (scripts/release-bump-checks-ready.py).
#
# Exit 0 with ready=true: enqueue head_sha (pr_id is the PR node id).
# Exit 0 with ready=false: the PR is already merged or closed; nothing to do
#   (await-bump in the calling workflow decides whether that is a failure).
# Anything else exits non-zero: a guard refused, a read failed, the head moved,
#   changes were requested, a check failed, or the wait timed out. A read that
#   fails is never "nothing wrong".
set -euo pipefail

: "${REPO:?REPO is required}" "${PR:?PR is required}" "${GITHUB_OUTPUT:?}" "${RUNNER_TEMP:?}"
WAIT_SECONDS=${WAIT_SECONDS:-2700}
APP_LOGIN='mctl-gitops-pr[bot]'
# The required status checks of ruleset main-protection (id 18465404). Keep in
# step with the ruleset; tests/test_release_bump_enqueue.py pins these to the
# job ids tests/test_required_check_job_ids.py guards.
REQUIRED_CHECKS=cloudflare-plan,reserved-hosts,validate
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

die() { echo "::error::$*"; exit 1; }
not_ready() { echo "::notice::$*"; echo "ready=false" >> "$GITHUB_OUTPUT"; exit 0; }

[[ "$PR" =~ ^[0-9]+$ ]] || die "no pull request number (got '${PR}'); not enqueueing."

# --- One read of the PR; every later check is pinned to this head. ---------
if ! info=$(gh api "repos/${REPO}/pulls/${PR}" \
      --jq '[.head.sha, .changed_files, .user.login, (.head.repo.full_name // ""), .head.ref, .state, .merged, .node_id] | @tsv'); then
  die "could not read #${PR}; not enqueueing."
fi
IFS=$'\t' read -r head_sha expected author head_repo head_ref state merged pr_id <<<"$info"
[[ "$head_sha" =~ ^[0-9a-f]{40}$ ]] || die "#${PR} has no readable head sha; not enqueueing."
[[ -n "$pr_id" ]] || die "#${PR} has no node id; not enqueueing."
if [ "$merged" = true ]; then not_ready "#${PR} is already merged."; fi
if [ "$state" = closed ]; then not_ready "#${PR} is closed."; fi
[ "$state" = open ] || die "#${PR} is in state '${state}'; not enqueueing."
[ "$author" = "$APP_LOGIN" ] || die "#${PR} is authored by ${author}, not ${APP_LOGIN}; it needs a human merge."
[ "$head_repo" = "$REPO" ] || die "the head of #${PR} is in '${head_repo}', not ${REPO}; it needs a human merge."
case "$head_ref" in release-bump/?*) ;; *) die "#${PR} is on '${head_ref}', not a release-bump/ branch." ;; esac

# --- The file list, read in full, against the auto-merge protected paths. ----
if ! files=$(gh api --paginate "repos/${REPO}/pulls/${PR}/files?per_page=100" \
      --jq '.[] | [.filename, (.previous_filename // "")] | @tsv'); then
  die "could not list the files of #${PR}; not enqueueing."
fi
listed=$(printf '%s' "$files" | grep -c . || true)
[ "$listed" = "$expected" ] || die "#${PR} reports ${expected} changed files but ${listed} were listed; not enqueueing."
# One protected-path list: the single-line protected_re of auto-merge.yml, read
# from this checkout of main (tests/test_auto_merge_protected_paths.py keeps it
# a single line). Not found exactly once is a refusal, never "nothing protected".
protected_re=$(sed -n "s/^[[:space:]]*protected_re='\([^']*\)'[[:space:]]*\$/\1/p" "$root/.github/workflows/auto-merge.yml")
[ -n "$protected_re" ] && [ "$(printf '%s\n' "$protected_re" | wc -l)" -eq 1 ] \
  || die "could not read protected_re from auto-merge.yml; not enqueueing."
rc=0
protected=$(printf '%s\n' "$files" | tr '\t' '\n' | grep -E "$protected_re") || rc=$?
[ "$rc" -le 1 ] || die "path check failed (grep exit ${rc}); not enqueueing."
[ -z "$protected" ] || die "#${PR} touches paths that need a human merge: $(printf '%s' "$protected" | tr '\n' ' ')"

# --- Only an image tag moves. ------------------------------------------------
gh api -H "Accept: application/vnd.github.diff" "repos/${REPO}/compare/main...${head_sha}" > "$RUNNER_TEMP/bump.diff" \
  || die "the diff of ${head_sha} could not be read; not enqueueing."
python3 "$root/scripts/release-bump-diff-guard.py" < "$RUNNER_TEMP/bump.diff" \
  || die "the diff of #${PR} is not a pure image tag move; it needs a human merge."

# --- Wait for the approval on head_sha and for green checks. ---------------
deadline=$((SECONDS + WAIT_SECONDS))
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
      10) echo "waiting for checks: ${verdict}" ;;
      *) die "#${PR} is not mergeable: ${verdict}" ;;
    esac
  else
    echo "waiting for an approval on ${head_sha} (review decision ${decision})"
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    die "#${PR} was not approved and green within $((WAIT_SECONDS / 60)) minutes; not enqueueing."
  fi
  sleep 30
done
