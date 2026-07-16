# Design: incident-1784173500

## Confidence: MEDIUM

This is more substantiated than a guess (it is backed by a live, reproduced
HTTP 500 from the Argo Workflows Server, plus a matching in-repo comment
that already documents the same underlying database defect), but the exact
causal link to the "run"/"run-fallback" pod's exit code 1 is inferred from
timing, not from the pod's own stdout (which is unrecoverable — see
requirements.md). The implementer should confirm with a live test (Tasks
step 4) before treating this as fully closed.

## Diagnosis

`platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml` (lines
~85-107) already documents a known defect in the Argo Workflows Postgres
persistence config:

- `nodeStatusOffLoad` is deliberately set to `false`.
- Because `schema_history` was already stamped at the latest migration
  version by an earlier (broken) config, Argo's built-in migrate framework
  now skips creating the `argo_workflows` offload table on controller
  startup, even though the table does not physically exist in the
  `argo-workflows` database on `shared-pg-rw.platform-db.svc`.
- The comment's conclusion is: "the error path is gone... no shared-pg DDL
  is needed", i.e. the missing table only affects an internal background
  GC pass that logs harmlessly every ~5 minutes, with no live-traffic
  impact, because offload is off.

That conclusion is disproven by direct testing performed during this
incident-responder run: a plain `GET /api/v1/workflows/argo-workflows`
against the live Argo Workflows Server (the same "list workflows" call any
client — including whatever populates `type: workflow_failed` /
`source: argo-workflows` incidents, and potentially the mctl-agents
run-orchestrator's own startup/status checks — would make) returns HTTP 500
with the *exact* error text from the comment:
`relation "argo_workflows" does not exist (SQLSTATE 42P01)`. This is not
confined to a background GC log line; it is surfaced synchronously to API
callers on a basic list query, while single-object GET by name (which
does not hit this code path) works fine.

Separately, the `run` and `run-fallback` steps of `mctl-agents-incidents-*`
both fail with a generic `exit code 1` after only 11-14 seconds — on *both*
the primary account (`claude-code-oauth-token`) and the independent fallback
account (`claude-code-oauth-token-2`). Two independent credentials failing
identically, this fast, rules out a token-specific auth problem and rules
out the leading theory from the four earlier rejected proposals
(incident-17840763/781/799/817): Claude API budget exhaustion, which would
require many tool calls over a longer wall-clock time to actually exhaust a
budget (confirmed live: `SERVICE_AGENT_BUDGET_USD=5.00` in this agent's own
environment, already raised from the original 2.0 by the one proposal that
did merge — incident-17840745/PR#55 — and the failures continued anyway,
which independently confirms budget was never the real cause). An 11-14s
failure on both accounts is much more consistent with a shared dependency
that both attempts hit immediately at startup — such as an incident-listing
or workflow-status call against the same broken Argo Workflows List API —
than with anything in the per-incident diagnosis loop.

The `workflow_failed` alert type has no pattern-matched skill in the
platform, which is why these incidents accumulate in `analyzing` instead of
auto-resolving, and why 16+ near-identical incidents built up in the queue.

## Proposed Fix

**Fix A (primary, requires DB access — flag for a human operator with
`shared-pg` credentials, this agent has none):**
Reconcile the Postgres `schema_history` for the `argo-workflows` database on
`shared-pg-rw.platform-db.svc` so Argo's migrate framework actually creates
the `argo_workflows` table it believes already exists. Concretely: inspect
the migration-tracking table (commonly `schema_history` /
`argo_db_version`) for the row corresponding to the offload-table-creation
step, and delete/rewind that single row so the controller's built-in
migration runner re-applies it on next restart. Do **not** hand-write a
`CREATE TABLE argo_workflows (...)` — the column/index layout is owned by
Argo's migrate framework and must match its expectations exactly, or future
Argo Workflows chart upgrades may fail to reconcile further migrations.
Verify by restarting the `argo-workflows-workflow-controller` deployment
after the rewind and confirming the table now exists.

**Fix B (safe, GitOps-only, apply regardless of Fix A's timing):**
File: `platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml`
Field: the comment block above `nodeStatusOffLoad: false` (~line 95-101)
Current text asserts the missing-table error path is fully inert:
```
            # ... (when tableName collided with the archive table),
            # and after correcting tableName the offload table no longer exists
            # in the DB (Argo's migrate framework skips creating it because
            # schema_history was already stamped at the latest version by the
            # earlier broken config), so the GC now logs
            # `relation "argo_workflows" does not exist` every ~5 min. With
            # offload off the controller never creates or queries that table,
            # so the error path is gone — and no shared-pg DDL is needed.
```
New text (correcting the disproven assumption, so the next engineer who
reads this does not re-conclude "harmless" and skip the DB fix):
```
            # ... (when tableName collided with the archive table),
            # and after correcting tableName the offload table no longer exists
            # in the DB (Argo's migrate framework skips creating it because
            # schema_history was already stamped at the latest version by the
            # earlier broken config), so the GC logs
            # `relation "argo_workflows" does not exist` every ~5 min.
            # CORRECTION (2026-07-16, incident-1784173500): this is NOT fully
            # inert. `GET /api/v1/workflows/{namespace}` (plain list, no
            # offload involved) reproducibly returns HTTP 500 with this same
            # error to any caller. This has been observed correlating with
            # mctl-agents-run cron failures (incident-responder, shepherd,
            # issue-poll). A DB-side fix (recreate argo_workflows via the
            # migrate framework — see agents-state/mctl-gitops/proposals/
            # incident-1784173500/) is required; this is not purely cosmetic.
```

## Scope

Minimal. Fix A is a one-time DB schema reconciliation (no application code or
Helm value changes). Fix B only edits an explanatory comment so the known
defect is not re-dismissed as inert by future readers — it changes no
runtime behavior. Do not touch unrelated Argo Workflows settings
(archiveTTL, resource limits, ingress, etc.) in this pass.
