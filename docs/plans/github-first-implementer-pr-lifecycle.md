# GitHub-first implementer PR lifecycle

Status: active rollout (phase A)

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

## Backlog gate

Before phase B, produce one row per initial PR containing proposal purpose,
head SHA, review decision, required checks, mergeability, projected status and
next action.

- Approved and clean: #66, #71, #594, #596, #598, #665, #666.
- Changes requested: #69, #70.
- Merge conflict: #584, #597.
- Merge conflict plus changes requested: #595.

Every PR must end as `merged`, `rejected` with a superseded/no-op reason, or
`needs-triage` with an actionable code and owner. In particular, reconciliation
must repair #66 (`review-stuck`) and the missing PR URLs for #71 and #598.

## Phase B

After the backlog report is accepted:

1. Resolve or close the three conflict branches without re-running Tier 2.
2. Complete review-fix loops for #69, #70 and #595.
3. Change only the mctl-gitops steward entry to `merge_mode=when-green`.
4. Resume the implementer cron with `max_proposals=1`.

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
