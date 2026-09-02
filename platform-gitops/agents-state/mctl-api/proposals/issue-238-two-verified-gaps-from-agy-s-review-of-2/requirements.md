# Audit StartDevLoopWorkflow and test the use_temporal MCP routing branch

## Context

Issue #238 records two findings from agy's review of PR #236 (merged as
`c0f2f560`) that were independently re-verified against `main` and confirmed
real, even though neither is a defect in #236 itself (that PR only touched
`ApproveDevLoopWorkflow` and added the `mctl_approve_dev_loop` tool).

1. `StartDevLoopWorkflow` (`internal/api/handlers_dev_loop.go:69`) starts a
   durable `DevLoopWorkflow` on Temporal — a state-changing, admin-only,
   control-plane action that pins agent versions and commits the platform to
   a run — but calls `h.logAudit` on none of its outcomes. After #236,
   `ApproveDevLoopWorkflow` writes an audit entry on all three of its
   branches (not-found failure, signal failure, success — lines 148, 160,
   173). `StartDevLoopWorkflow` writes zero, on any of its four branches
   (missing `issue_url`, invalid JSON, invalid `issue_url`, Temporal RPC
   failure, success). This asymmetry means the more consequential of the two
   dev-loop actions (starting a new workflow vs. approving an existing one)
   is the one that leaves no trace.

2. `mctl_trigger_issue`'s `use_temporal` boolean (`internal/mcp/server.go:2513-2526`)
   routes the MCP tool to a completely different backend endpoint
   (`POST /api/v1/agents/dev-loop/start` with a JSON body vs.
   `POST /api/v1/operations/mctl-agents-investigate/execute` with form-style
   string params) but `git grep use_temporal -- '*_test.go'` returns nothing.
   Neither direction is guarded: a regression that always takes the
   Temporal branch, or one that never takes it, would ship silently. #236
   added exactly this class of guard for the sibling `mctl_approve_dev_loop`
   tool (`TestToolApproveDevLoop_PostsToDevLoopApprovePath`,
   `TestToolApproveDevLoop_NeverHitsOperationsExecute`); this proposal adds
   the same class of guard for the branch that predates it.

The issue explicitly identifies two other agy findings ("`StartDevLoopWorkflow`'s
400 paths are untested" and "`shepherdBlocks` is never exercised") as
verified FALSE and asks that they not be re-raised; this proposal does not
touch either.

## User stories

- AS a platform operator reviewing the audit log I WANT every
  `StartDevLoopWorkflow` call (successful or not) recorded SO THAT I can see
  who started a `DevLoopWorkflow`, for which issue, and with what outcome,
  the same way I can already see who approved one.
- AS a maintainer of `internal/mcp/server.go` I WANT an automated test that
  pins `use_temporal`'s routing behavior SO THAT a future change to
  `toolTriggerIssue` cannot silently break either the Temporal path or the
  legacy operations-execute path.

## Acceptance criteria (EARS)

- WHEN `StartDevLoopWorkflow` receives a request with an empty or malformed
  JSON body (decode error) THE SYSTEM SHALL return 400 and SHALL NOT write
  an audit entry.
- WHEN `StartDevLoopWorkflow` receives a request with `issue_url` missing or
  empty THE SYSTEM SHALL return 400 and SHALL NOT write an audit entry.
- WHEN `StartDevLoopWorkflow` calls `TemporalClient.StartDevLoopWorkflow` and
  it returns `temporalclient.ErrInvalidIssueURL` THE SYSTEM SHALL return 400
  and SHALL NOT write an audit entry (mirrors the "caller input, not a
  platform action" boundary #236 drew for `ApproveDevLoopWorkflow`'s
  request-validation branches, which also do not audit).
- WHEN `StartDevLoopWorkflow` calls `TemporalClient.StartDevLoopWorkflow` and
  it returns any other error (a Temporal RPC/connectivity failure) THE
  SYSTEM SHALL return 502 and SHALL write an audit entry with
  `Operation: "dev-loop-start"`, `Status: "failed"`,
  `RiskLevel: string(operations.RiskMedium)`, empty `WorkflowName`, and a
  `Message` describing the failure.
- WHEN `TemporalClient.StartDevLoopWorkflow` succeeds THE SYSTEM SHALL write
  an audit entry with `Operation: "dev-loop-start"`, `Status: "succeeded"`,
  `RiskLevel: string(operations.RiskMedium)`, and `WorkflowName` set to the
  returned workflow ID, written after the Temporal call returns (the ID is
  not known beforehand) and before or alongside the 202 JSON response.
- WHILE constructing the audit entry's `Parameters` THE SYSTEM SHALL include
  the request's `issue_url` (mirrors `ApproveDevLoopWorkflow` including its
  own request fields, e.g. `approver`/`reason`, in `Parameters`).
- WHEN `mctl_trigger_issue` is invoked with `use_temporal: true` THE SYSTEM
  SHALL POST to `/api/v1/agents/dev-loop/start` with a JSON body containing
  `issue_url`, and SHALL NOT POST to
  `/api/v1/operations/mctl-agents-investigate/execute`.
- WHEN `mctl_trigger_issue` is invoked with `use_temporal` absent, or with
  `use_temporal: false` THE SYSTEM SHALL POST to
  `/api/v1/operations/mctl-agents-investigate/execute`, and SHALL NOT POST
  to `/api/v1/agents/dev-loop/start`.
- IF the audit log is not configured (`h.opts.AuditLog == nil`) THEN THE
  SYSTEM SHALL continue handling the request unchanged (the existing
  `logAudit` nil-check already guarantees this; no new behavior is required,
  only preserved).

## Out of scope

- Any change to `ApproveDevLoopWorkflow`, `GetDevLoopWorkflow`, or
  `mctl_approve_dev_loop` — both are already audited/tested per #236 and per
  the issue's own "checked and FALSE" list.
- Testing `StartDevLoopWorkflow`'s malformed-JSON-body 400 path as a *new*
  gap — it already has no dedicated test today, same as before this issue,
  but the issue explicitly scopes the "400 paths are untested" claim as
  FALSE overall (two of three paths are covered) and does not ask for the
  third. This proposal adds audit-log coverage to all 400 paths as a side
  effect of asserting "no audit entry", which incidentally also exercises
  the malformed-JSON path, but does not add a standalone test file/case
  whose sole purpose is that path.
- Making agy a blocking gate on this repo (issue references #145 for that
  separately).
- Any change to the `DevLoopWorkflow` Temporal orchestrator itself
  (`orchestrator/temporal/workflows/dev_loop.py`, out of this repo's scope).
- Adding audit logging to any other unaudited handler not named in the
  issue.

## Open questions

- None. The issue specifies the exact operation name (`dev-loop-start`),
  risk level (`operations.RiskMedium`), and success/failure `WorkflowName`
  semantics; both are directly analogous to the already-merged
  `ApproveDevLoopWorkflow` audit shape in the same file, so implementation
  has a concrete precedent to copy.
