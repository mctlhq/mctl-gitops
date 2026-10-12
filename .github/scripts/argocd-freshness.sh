#!/usr/bin/env bash
# Verify that every Argo CD Application tracking this repo's `main` has
# resolved the pushed commit (or a descendant of it).
#
# Why this exists: argocd_app_info carries no `revision` label, so "the app
# is Synced but on an older commit than main" cannot be expressed as a
# Prometheus rule. On 2026-09-01 that state went unnoticed for the whole
# poll+cache window (#970). This check asks the Argo CD API directly, right
# after the push whose SHA it knows.
#
# Usage:
#   argocd-freshness.sh <sha>            # needs ARGOCD_SERVER, ARGOCD_TOKEN
#   argocd-freshness.sh --self-test      # exercises the extraction on fixtures
#
# Exit 0 when every tracked source is at <sha> or newer and no tracked app
# is left OutOfSync by a failed sync operation, 1 otherwise.
#
# Resolving the commit is not the same as applying it (#1855): on 2026-10-12
# two bumps landed seconds apart, the auto-sync of a multi-source app pinned
# its chart and $values sources to different commits, failed on all retries
# and stayed OutOfSync on the previous image, while status.sync.revisions
# already pointed at the new commit and this check reported green.
set -euo pipefail

REPO_RE='^https://github\.com/mctlhq/mctl-gitops(\.git)?$'
ARGOCD_SERVER="${ARGOCD_SERVER:-https://ops.mctl.ai}"

# Print "<app>\t<source-index>\t<revision>\t<failed-phase>" for every source
# of every Application that points at this repository's main branch.
# <failed-phase> is the last operation's phase (Error / Failed) when that
# operation failed AND the app is still not Synced, empty otherwise: a failed
# operation on an app that has since converged is history, not drift.
#
# Sources and status.sync.revisions are parallel arrays; single-source apps
# expose spec.source / status.sync.revision instead, so both shapes are
# folded into the same list-of-sources form first.
tracked_sources() {
  jq -r --arg re "$REPO_RE" '
    .items[]
    | .metadata.name as $name
    | ((.spec.sources // [.spec.source])) as $sources
    | ((.status.sync.revisions // [.status.sync.revision]) // []) as $revs
    | (.status.operationState.phase // "") as $phase
    | (if (.status.sync.status // "") != "Synced"
          and ($phase == "Error" or $phase == "Failed")
       then $phase else "" end) as $failed
    | range(0; $sources | length) as $i
    | $sources[$i]
    | select((.repoURL // "") | test($re))
    | select(.targetRevision == "main")
    | [$name, ($i | tostring), ($revs[$i] // ""), $failed]
    | @tsv
  '
}

# Return the tracked sources whose revision does not contain <sha>, or whose
# app is stuck OutOfSync after a failed sync operation.
stale_sources() {
  local sha="$1"
  while IFS=$'\t' read -r app idx rev failed; do
    if [ -n "$failed" ]; then
      printf '%s\t%s\t%s\n' "$app" "$idx" "${rev:-(no revision)} (OutOfSync, last sync ${failed})"
      continue
    fi
    if [ -z "$rev" ]; then
      printf '%s\t%s\t%s\n' "$app" "$idx" "(no revision)"
      continue
    fi
    if ! git cat-file -e "${rev}^{commit}" 2>/dev/null; then
      printf '%s\t%s\t%s\n' "$app" "$idx" "$rev (unknown commit)"
      continue
    fi
    if ! git merge-base --is-ancestor "$sha" "$rev"; then
      printf '%s\t%s\t%s\n' "$app" "$idx" "$rev"
    fi
  done
}

# Zero tracked sources cannot be right for this repository — it means the
# response shape changed (e.g. a `fields=` projection dropping nested
# paths, which is how the first live run passed vacuously), not that
# everything is fresh.
require_tracked() {
  local total="$1"
  if [ "$total" -eq 0 ]; then
    echo "no Application source tracking mctl-gitops main was found in the API response" >&2
    return 1
  fi
}

self_test() {
  local fixture out
  fixture='{"items":[
    {"metadata":{"name":"single"},"spec":{"source":{"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"main"}},"status":{"sync":{"revision":"aaa"}}},
    {"metadata":{"name":"multi"},"spec":{"sources":[
        {"repoURL":"https://argoproj.github.io/argo-helm","targetRevision":"0.72.5"},
        {"repoURL":"https://github.com/mctlhq/mctl-gitops","targetRevision":"main","ref":"values"}]},
     "status":{"sync":{"revisions":["0.72.5","bbb"]}}},
    {"metadata":{"name":"tag-pinned"},"spec":{"source":{"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"2.6.3"}},"status":{"sync":{"revision":"2.6.3"}}},
    {"metadata":{"name":"other-repo"},"spec":{"source":{"repoURL":"https://github.com/mctlhq/mctl-api.git","targetRevision":"main"}},"status":{"sync":{"revision":"ccc"}}},
    {"metadata":{"name":"never-synced"},"spec":{"source":{"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"main"}},"status":{}},
    {"metadata":{"name":"mixed-revisions"},"spec":{"sources":[
        {"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"main","path":"chart"},
        {"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"main","ref":"values"}]},
     "status":{"sync":{"status":"OutOfSync","revisions":["ddd","ddd"]},"operationState":{"phase":"Error"}}},
    {"metadata":{"name":"failed-then-converged"},"spec":{"source":{"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"main"}},
     "status":{"sync":{"status":"Synced","revision":"eee"},"operationState":{"phase":"Failed"}}},
    {"metadata":{"name":"sync-running"},"spec":{"source":{"repoURL":"https://github.com/mctlhq/mctl-gitops.git","targetRevision":"main"}},
     "status":{"sync":{"status":"OutOfSync","revision":"fff"},"operationState":{"phase":"Running"}}}
  ]}'
  out=$(printf '%s' "$fixture" | tracked_sources)
  expected=$'single\t0\taaa\t\nmulti\t1\tbbb\t\nnever-synced\t0\t\t\nmixed-revisions\t0\tddd\tError\nmixed-revisions\t1\tddd\tError\nfailed-then-converged\t0\teee\t\nsync-running\t0\tfff\t'
  if [ "$out" != "$expected" ]; then
    echo "self-test FAILED: tracked_sources produced:" >&2
    printf '%s\n' "$out" >&2
    exit 1
  fi
  # A failed operation that left the app OutOfSync is stale even though its
  # revision already contains the commit (#1855). No git lookup is needed for
  # that verdict, so the fixture SHA does not have to exist.
  out=$(printf 'mixed-revisions\t1\tddd\tError\n' | stale_sources "ddd")
  if [ "$out" != $'mixed-revisions\t1\tddd (OutOfSync, last sync Error)' ]; then
    echo "self-test FAILED: a failed sync left OutOfSync must be stale, got: ${out:-(nothing)}" >&2
    exit 1
  fi
  # An empty or unexpectedly shaped response must fail, never pass.
  local empty_total
  empty_total=$(printf '{"items":[{"metadata":{"name":"only-name"}}]}' | tracked_sources | wc -l | tr -d ' ')
  if [ "$empty_total" != "0" ] || require_tracked "$empty_total" 2>/dev/null; then
    echo "self-test FAILED: a response without sources must be rejected" >&2
    exit 1
  fi
  echo "self-test OK"
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi

sha="${1:?usage: $0 <sha> | --self-test}"
: "${ARGOCD_TOKEN:?ARGOCD_TOKEN is required}"

# No `fields=` projection: the API honours only some nested paths
# (`items.spec` yes, `items.status.sync.revisions` no) and silently drops
# the rest, which made the first live run report "all 0 tracked sources".
# The full list is ~1.5 MB for 46 apps; that is fine once per push.
if ! apps=$(curl -sSf --max-time 60 \
  -H "Authorization: Bearer ${ARGOCD_TOKEN}" \
  "${ARGOCD_SERVER}/api/v1/applications"); then
  echo "failed to list applications from ${ARGOCD_SERVER} (network, TLS or token problem — see curl output above)" >&2
  exit 1
fi

# The revision an app reports may be NEWER than the checkout we run in
# (bot bumps land every few minutes), so make sure those commits are local.
git fetch -q origin main

total=$(printf '%s' "$apps" | tracked_sources | wc -l | tr -d ' ')
require_tracked "$total"
stale=$(printf '%s' "$apps" | tracked_sources | stale_sources "$sha")
if [ -z "$stale" ]; then
  echo "all ${total} tracked sources are at ${sha} or newer"
  exit 0
fi
echo "sources still behind ${sha}:"
printf '%s\n' "$stale"
exit 1
