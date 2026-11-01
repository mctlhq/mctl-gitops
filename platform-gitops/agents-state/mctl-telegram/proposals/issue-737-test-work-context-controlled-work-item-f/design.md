# Design: issue-737-test-work-context-controlled-work-item-f

## Current state
The Telegram side of the flow under observation already exists:
- `internal/agent/control/work.go`: `WorkHandler.Handle` handles the `/mctl work` subcommands. `handleLink` binds the account. `handleOpen` canonicalises the issue URL with `workctx.CanonicalIssueURL`, resolves the linked actor, reuses or creates the per-thread binding (`Store.GetWorkItemBinding` / `UpsertWorkItemBinding`), and submits a `start` execution request (`workctx.ExecutionKindStart`) with an idempotency key from `workctx.IdempotencyKey(chat, msg, "start", 0)`. `handleWorkStatus` and `formatRequestState` print the request state, for example "claimed — the platform is starting it."
- `internal/workctx/client.go`, `envelope.go`, `errors.go`: the mctl-api WorkItem REST client and its typed error mapping (`workctxErrText`).
- `internal/db/work_item_bindings.go`: stores each Saved Messages thread's binding to a WorkItem.

This issue needs none of that code to change. The issue is the input to the flow, not a change to it.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag `0.119.0`. `workContext.enabled: true`, `featureEnabled: true`, `tenant: mctl`, token from Vault `platform/mctl-api/surface-tokens` / `telegram-token`. `HUMAN_INPUT_ENABLED: "true"`. So `/mctl work` is enabled in production, consistent with the session the issue describes.
- No mctl MCP read tools were called. They were not needed, because this proposal asserts nothing about runtime behaviour beyond the gitops values above.

## Proposed solution
No change. This proposal is the evidence artifact of the observed DevLoop
investigation. Expected handling:
1. Keep it at `proposed` and do not approve it.
2. When the owner has recorded the session evidence on #443, end the DevLoop by abandoning or rejecting it (for example `mctl_abandon_dev_loop` on `dev-loop-mctlhq-mctl-telegram-737`).

## Alternatives
- Invent a small change (for example a test for `formatRequestState`) so the proposal is "implementable". Rejected: the issue explicitly forbids implementation, and a real diff could be approved and merged by accident.
- File a clarification question. Rejected: the issue already answers the only question that matters (do not implement).
- Write no proposal. Rejected: the session must observe a completed investigation with a proposal, and the orchestrator expects the three files.

## Platform impact
- Migrations: none. Backward compatibility: unaffected. Resources: none beyond the investigation run already spent.
- Risk: someone approves the proposal by mistake. Mitigation: requirements and tasks contain no code-changing task, and the implementer has nothing to build. A parked DevLoop is closed by abandoning it.
