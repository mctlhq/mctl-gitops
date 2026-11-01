# Design: issue-737-test-work-context-controlled-work-item-f

## Current state
The Telegram work-context adapter from #443 is already shipped:
- `internal/agent/control/work.go` — `WorkHandler.Handle` dispatches `/mctl link` (`handleLink` -> `workctx.Client.RedeemLink`), `/mctl work <issue-url>` (`handleOpen`: `CreateWorkItem`, `UpsertWorkItemBinding`, then `RequestExecution` with `Kind: workctx.ExecutionKindStart` and an idempotency key from `workctx.IdempotencyKey(chat, msg, "start", 0)`; a bound item with no recorded start request redoes create + start), and `/mctl work status` (`handleWorkStatus`: `GetWorkItem`, `TouchWorkItemBindingState`, then `renderRequestLine` / `formatRequestState`).
- `internal/workctx/client.go` — relay client to mctl-api (`CreateWorkItem`, `GetWorkItem`, `RequestExecution`, `GetExecutionRequest`, `ListExecutionRequests`, `AddSurfaceRef`), scoped to one tenant.
- `internal/db/work_item_bindings.go` — per-user/chat binding store (`LatestWorkItemBinding`, `SetWorkItemBindingRequest`).

Everything the issue asks for is exercising this existing code; nothing in it needs to change.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: `image.tag: "0.119.0"`, hosts `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`, and `workContext.enabled: true`, `featureEnabled: true`, `tenant: mctl`, token from Vault `platform/mctl-api/surface-tokens` / `telegram-token`. The comment there records all four owner enablement steps done 2026-10-04. So `/mctl work` is live in production.
- mctl MCP tools were not called. Live pod state, logs and the actual WorkItem/request ids from the session were not observed by this run.

## Proposed solution
No change. The proposal is intentionally empty of implementation work:
1. The DevLoop investigation (this run) is the observed `start` execution; once its request reads `fulfilled, execution <id>` in `/mctl work status`, and the same WorkItem renders at the portal `/work-items/<id>`, the session evidence is complete.
2. The owner records that evidence on #443 (and the REST traces for mctl-api#341).
3. This proposal is left unapproved and then rejected or its DevLoop abandoned; #737 is already closed.

## Alternatives
- Propose a real improvement found while reading `work.go` (for example richer status output): dropped, the issue explicitly forbids implementation and the item must stay a clean control.
- Propose additional automated tests for the session flow: dropped for the same reason; `internal/agent/control/work_test.go` and `internal/workctx/client_test.go` already cover the handlers, and any new test work belongs in a separate issue.
- Skip writing a proposal: dropped, the pipeline requires the triplet and an explicit "do not implement" proposal is the safest artefact.

## Platform impact
- Migrations: none. Backward compatibility: unaffected. Resources: none beyond the one investigator run already spent.
- Risk: someone approves the proposal and the implementer opens an empty or invented PR. Mitigation: every file states no-implementation; reviewer should reject or abandon the DevLoop (`dev-loop-mctlhq-mctl-telegram-737`).
