# GitHub-first implementer PR lifecycle

Status: phase A live; awaiting backlog-decision acceptance

## Problem

Implementer PRs can exist on GitHub while their proposal remains
`in-progress`, lacks `pr`, or carries a stale `review-stuck` value. The old
fallback then force-reprocessed every `in-progress` proposal, creating
duplicate work and rapidly consuming subscription quota.

At the start of this rollout there were 12 open `feat/agents-*` PRs:

- `mctl-agents`: #66, #69, #70, #71
- `mctl-gitops`: #584, #594, #595, #596, #597, #598, #665, #666

## Invariants

- GitHub is authoritative for branch, PR, review, check and merge state.
- `.status.yaml` is a durable projection and workflow coordination record.
- The model runs only after a successful GitHub preflight proves that neither
  a canonical PR nor a useful deterministic result branch already exists.
- Failed/no-commit attempts move to `needs-triage`; automation never retries
  them without an operator-reviewed transition back to `accepted`.
- Shepherd and pr-steward have disjoint active ownership. Reconciliation may
  update status for every service but never reviews, fixes or merges code.

## Implementation

### mctl-agents 1.20.0

- Shared read/merge/write status helper preserves all fields unless a caller
  explicitly removes one.
- Implementer adopts open/merged/closed PRs, opens a missing PR for an existing
  useful branch, and fails closed when GitHub cannot be queried.
- Attempts carry an ID and expiry. Failures carry structured `code`, `stage`
  and `message` fields.
- `--force` is removed; scheduled runs process at most one accepted proposal.
- Reconcile scans every service, restores missing PR URLs, heals stale open
  state, records merge conflicts, and projects merged/closed terminal state.

### GitOps phase A

- Implementer cron stays suspended while the existing backlog is reconciled.
- Reconcile runs every 15 minutes with mctl-agents 1.20.0.
- `mctl-gitops` is added to pr-steward with exact
  `head_prefix=feat/agents-`, `merge_method=merge`, and `merge_mode=never`.
- Shepherd continues to skip `mctl-gitops`; therefore only steward can drive
  its active PRs.

Phase A was merged in mctl-gitops #668. The first new reconciler tick,
`mctl-agents-reconcile-1785321900`, succeeded at 10:45 UTC on 2026-07-29 and
wrote projection commit `6ce9a750`. It restored the missing PR URLs for #71
and #598, converted #66 from stale `review-stuck` to actionable
`needs-triage`, and projected all current conflicts without invoking a model.

## Backlog gate

Snapshot after the first phase-A reconciliation:

| PR | Purpose | Head SHA | Review / checks | Mergeability | Projection | Recommended decision |
|---|---|---|---|---|---|---|
| mctl-agents #66 | Distinguish wedged implementer failures in batch exit status | `ad69360a` | Approved; green | Conflict | `needs-triage: merge-conflict` | Close as superseded by 1.20.0 structured triage and one-proposal batching |
| mctl-agents #69 | Run accepted proposals concurrently with AnyIO | `851f5b70` | Changes requested (P2); green | Conflict | `needs-triage: merge-conflict` | Close; concurrency contradicts the quota-safe `max_proposals=1` invariant |
| mctl-agents #70 | Run accepted proposals in a thread pool | `1f49d741` | Changes requested (P2); green | Conflict | `needs-triage: merge-conflict` | Close for the same reason as #69 |
| mctl-agents #71 | Add a 15-minute wall-clock timeout per model call | `1d0b0d7a` | Approved; green | Conflict | `needs-triage: merge-conflict` | Rebase/salvage the timeout on current main, then re-review |
| mctl-gitops #584 | Render the paused OpenClaw ServiceMonitor only when replicas exist | `4a599cf0` | Approved; green | Conflict | `needs-triage: merge-conflict` | Resolve the values conflict, validate the render gate, then merge |
| mctl-gitops #594 | Document the Argo workflow persistence-table diagnosis | `838ba7f1` | Approved; green | Clean | `implemented` | Close as no-op documentation; it does not recreate the missing table |
| mctl-gitops #595 | Alert when agents pipelines fail without a recent success | `52b51a8a` | Changes requested (P2); green | Conflict | `needs-triage: merge-conflict` | Close as stale: it assumes the removed fallback flow and its regex is inconsistent |
| mctl-gitops #596 | Fail a hung issue-poll run after 30 minutes | `ef2d5ac5` | Approved; green | Clean | `implemented` | Merge |
| mctl-gitops #597 | Raise shepherd deadline to six hours and normalize an unset output | `aa20a829` | Approved; green | Conflict | `needs-triage: merge-conflict` | Close; six hours increases quota exposure, salvage output normalization separately if needed |
| mctl-gitops #598 | Add workflow log labels, git retry, and longer failure retention | `076cc1ea` | Approved; green | Clean | `implemented` | Merge |
| mctl-gitops #665 | Raise implementer deadline to four hours for unlimited batches | `aef7c764` | Approved; green | Clean | `implemented` | Close as superseded by the one-proposal cap |
| mctl-gitops #666 | Force a one-time quirestack-web rollout | `0a7a9483` | Approved; green | Clean | `implemented` | Close as stale: the incident is resolved and the app is Healthy/Synced |

Every PR must end as `merged`, `rejected` with a superseded/no-op reason, or
`needs-triage` with an actionable code and owner. The recommendations above
are a decision gate: phase B must not execute them until the report is
accepted.

## Phase B

After the backlog report is accepted:

1. Close the eight superseded, stale, or no-op PRs listed above and project
   their proposals as `rejected` with the specific reason.
2. Rebase and re-review #71 and #584 without re-running Tier 2.
3. Merge #596 and #598 after rechecking their exact head SHA and required
   checks.
4. Change only the mctl-gitops steward entry to `merge_mode=when-green`.
5. Resume the implementer cron with `max_proposals=1`.

The final merge gate is exact head SHA, approved review, green required checks,
no P1/P2 findings and no conflict. Roll back by returning `merge_mode` to
`never` and suspending the cron; no live-state imperative change is required.

## Acceptance

- No open `feat/agents-*` PR lacks a projected URL for more than 15 minutes.
- No expired `in-progress` proposal lacks a structured outcome.
- A model invocation is impossible when the canonical PR/branch already
  exists or GitHub preflight fails.
- Re-running reconciliation without GitHub changes produces no Git diff.
- All 12 initial PRs have an explicit terminal or actionable triage outcome.
