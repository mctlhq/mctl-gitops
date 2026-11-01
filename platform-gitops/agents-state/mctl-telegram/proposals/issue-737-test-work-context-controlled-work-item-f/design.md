# Design: issue-737-test-work-context-controlled-work-item-f

## Current state
The path the live session exercises already exists in the clone:

- `internal/agent/control/work.go`: `WorkHandler.Handle` dispatches `/mctl link`
  (`handleLink`), `/mctl work <issue-url>` (`handleOpen`), `/mctl work status`
  (`handleWorkStatus`), `/mctl work note` (`handleNote`) and `/mctl work resume`
  (`handleResume`). `handleOpen` creates or reuses the WorkItem binding, then
  submits a start request with kind `workctx.ExecutionKindStart` and an idempotency
  key from `workctx.IdempotencyKey(meta.ChatTGID, meta.TGMessageID, "start", 0)`.
  If the binding exists but no start request was recorded, it redoes the
  create-and-start step. `formatRequestState` renders the pending, claimed and
  fulfilled states that `/mctl work status` shows.
- `internal/workctx/client.go`, `envelope.go`, `errors.go`: the mctl-api
  work-context REST client. `workctxErrText` maps typed errors such as
  `execution_request_open` and `execution_active` to replies.
- `internal/db/work_item_bindings.go`: the persisted Telegram-chat-to-WorkItem
  binding.

Issue #737 asks only that this path be exercised against a real issue. It asks
for no change.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: the service is
  deployed in tenant `labs` with hosts `tg.mctl.ai` and
  `labs-mctl-telegram.mctl.ai`. The `workContext` block reads `enabled: true`,
  `featureEnabled: true`, `tenant: mctl`,
  `tokenVaultKey: platform/mctl-api/surface-tokens`,
  `tokenVaultProperty: telegram-token` and `apiBaseUrl: ""`. Its comment says the
  owner steps were done on 2026-10-04, so the adapter is on in production and the
  session can run against it.
- No mctl MCP read tools were called. Runtime state (logs, the WorkItem id, the
  request state) was not observed, and none of it is needed for a no-change
  proposal.

## Proposed solution
Change nothing. The deliverable is this proposal: the observable artifact of a
fulfilled `start` execution request. The proposal must not be approved. After the
owner records the evidence on #443, the DevLoop should be abandoned, not approved,
so that the implementer never runs.

## Alternatives
- Propose a small real change, such as more tests for `handleOpen`. Rejected: the
  issue explicitly forbids implementation, and an actionable proposal invites a
  mistaken approval.
- File a clarification question instead. Rejected: the issue is fully clear about
  the intent, and a question would delay the fulfilled state the session observes.
- Write a deliberately empty or failing proposal. Rejected: the session needs a
  normal, complete proposal to observe the success path.

## Platform impact
- Migrations: none. Backward compatibility: unaffected. Resources: none beyond
  this already-spent investigation run.
- Risk: someone approves the proposal and the implementer runs. Mitigation: the
  tasks change no files, so the implementer has nothing to commit and the proposal
  moves to needs-triage with no PR. The owner should abandon the loop instead.
