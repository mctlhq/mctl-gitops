# Design: issue-871-feat-mcp-bind-execution-to-readable-inte

## Current state
- `internal/mcp/workitems.go` `toolRequestWorkItemExecution` builds the body `{kind, expected_state_version, surface:"mcp", idempotency_key, resumed_from_execution_id?}` and POSTs it to `/api/v1/work-items/{id}/execution-requests` through `workItemCall`. That helper forwards the caller's own token (`effectiveToken`) and marks a 200 on POST as `replayed: true`. The tool has no `intent_id` argument.
- `internal/api/handlers_execution_requests.go` `CreateExecutionRequest` does the following, in order:
  - refuses the service principal (`xrCodeRequesterForbidden`);
  - checks visibility (`visibleWorkItem`) and the tenant role (`requireWorkItemRole(..., workItemExecutionRole)`; `workItemExecutionRole = operations.RoleDeveloper` in `internal/api/tenant_role.go`, so a viewer gets 403);
  - refuses execution-identity fields (`refuseExecutionIdentity`);
  - strictly decodes `executionRequestBody`, which already includes `IntentID *int64`;
  - builds the `Mutation` with `mutationFor`. A relayed token's surface wins, and a mismatched `surface` is refused (`internal/api/handlers_work_items.go:260`).
- `writeExecutionRequestError` maps `workitems.ErrIntentNotFound` to 404 `intent_not_found`.
- `internal/workitems/execution_requests.go` `CreateExecutionRequest`: under the item advisory lock it replays, checks the version, enforces one open request per item, then runs `checkRunnable`. For an intent it runs only `SELECT EXISTS (... work_item_intents WHERE work_item_id=$1 AND id=$2)`. Because the query is scoped to the item, a foreign item's or tenant's intent is already 404, but a NULL-text intent is accepted. `FulfilExecutionRequest` never looks at `intent_id`. `ClaimExecutionRequest` returns the request (with `intent_id`) and the item, but says nothing about whether the intent is readable.
- Redaction representation: `Store.Intent` / `Store.Intents` (`internal/workitems/store.go` ~943-1010) read `text IS NULL` as `TextRedacted=true` (`internal/workitems/types.go` `Intent.TextRedacted`). Nothing in the codebase sets the text to NULL except tests (`store_test.go:544`, `client_id_test.go:79`). The retention sweeper (mctl-api#353) is not implemented.
- `internal/workitems/snapshots.go`: snapshots are immutable canonical bytes sealed by the execution platform (`SealSnapshot`). mctl-api does not interpret `current_surface` / `surface_transition`; a grep finds neither anywhere in the repo. They are produced by mctl-agents (#573).
- Tests in place: `internal/mcp/workitems_test.go` (`TestRequestWorkItemExecutionSendsARequestNotAnExecution`, `...RefusesBadArgumentsWithoutCalling`, `...MarksAReplay`), `internal/api/handlers_execution_requests_test.go` (`TestExecutionRequests_ResumeRejectAndLapsedClaim` already covers a foreign `intent_id` returning 404), and `internal/workitems/execution_requests_test.go`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` listing: no `mctl-api` service directory under any tenant. mctl-api is not deployed as a tenant service in this checkout, so its deployed env and replicas could not be observed.
- `services/admins/mctl-agents-worker-exec/values.yaml`: image tag `1.114.1`, command `orchestrator.temporal.worker --role execution`. The file does not show whether this role claims `/execution-requests/claim`, so the claiming worker image is unconfirmed.
- mctl MCP tools were not called for this proposal. Live state (mctl-api image tag, whether any worker currently claims execution requests) was not observed and is recorded under Open questions.

## Proposed solution
1. MCP wrapper (`internal/mcp/workitems.go`, `toolRequestWorkItemExecution`)
   - Add an optional `mcplib.WithNumber("intent_id", ...)` argument. Validate it like `expected_state_version`: a float64 that is an integer, at least 1 and at most 2^53. Otherwise return a local tool error and make no HTTP call. When valid, set `body["intent_id"] = int64(v)`; when absent, set no key.
   - Update the tool description:
     - `intent_id` pins the intent the run acts on;
     - an unreadable (redacted) intent is refused with `intent_unavailable`;
     - another item's intent answers `intent_not_found`;
     - no other intent is ever substituted, and a replacement needs a new request with a new idempotency key.
   - Tool count is unchanged (no new tool), so the expectation in `server_test.go` does not move.
2. Store (`internal/workitems/execution_requests.go`)
   - Add `ErrIntentUnavailable = errors.New("intent text is unavailable")` and a helper `pinnedIntentState(ctx, q, itemID, id) (found, readable bool, err error)`, which runs `SELECT text IS NOT NULL FROM work_item_intents WHERE work_item_id=$1 AND id=$2`.
   - `CreateExecutionRequest`: replace the EXISTS query with the helper. Not found keeps `ErrIntentNotFound`; found but not readable returns `fmt.Errorf("workitems: intent %d of %s: %w", id, item, ErrIntentUnavailable)`. This runs after the replay check, so a replay of a request whose intent was later redacted still returns the original request and does not fork.
   - `FulfilExecutionRequest`: inside `lockedRequest`, after the claim-holder check and before `checkStart`/`resumeTx`, re-check a non-nil `x.IntentID` with the helper. Not readable returns `ErrIntentUnavailable`: the transaction aborts, no execution is attached, and the request stays claimed so the holder rejects it. A replayed fulfil (state already fulfilled) is not re-checked, because the execution already exists.
   - `ClaimExecutionRequest`: compute `intent_available` for a claimed request with an `intent_id` inside the same transaction. Return it from the store, either as a new field on `ExecutionRequest` that is serialized only from the claim, or as an extra return value. The API adds it to the claim response.
3. HTTP (`internal/api/handlers_execution_requests.go`)
   - Add `xrCodeIntentUnavailable = "intent_unavailable"`. In `writeExecutionRequestError`, map `ErrIntentUnavailable` to 409 with details `{"intent_id": ...}` (carried via a small `IntentUnavailableError{IntentID}` type that unwraps to the sentinel). Never include intent text.
   - `executionRequestRefusalCode` returns it for fulfil, so the refusal is audited (`auditExecutionRequestRefusal`) as `work_item.execution_request_fulfil_refused` with reason `intent_unavailable`.
   - Claim response: `writeExecutionRequest(w, 200, x, {"claim_token": ..., "intent_available": b})`, with `intent_available` present only when `intent_id` is set.
4. OpenAPI and docs: add `intent_unavailable` (409) to the create and fulfil responses and `intent_available` to the claim response in `internal/openapi`, if the spec is maintained there, and in the docs page describing work items.
5. Surface provenance on the request: no new code. The MCP wrapper already pins `surface:"mcp"`, and `mutationFor` refuses a relayed token that claims another surface. Tests prove the request row carries `surface=mcp` with `requested_by` from the token for a Telegram-origin item. Surface labels are never consulted by `internal/workitems/action_approvals.go`; a regression test pins that.
6. Per-execution provenance (for mctlhq/mctl-agents#960)
   - Why: today the investigator compares the new surface with the **item's origin**, because v1 executions carry no surface. An MCP->MCP resume over a Telegram origin therefore seals `surface_transition=true` (observed live on 2026-11-01, snapshot `cs_0c8288c65db5f2e917592fa112d1950b`). That breaks the acceptance line "MCP to MCP is not a transition".
   - What:
     - Add `Surface`, `RequestedBy` and `ActingPrincipal` (all `omitempty`) to `workitems.Execution`.
     - Fill them in `listExecutions`, and in the latest-execution read behind the work-item view, with a `LEFT JOIN work_item_execution_requests xr ON xr.execution_id = wie.id AND xr.state = 'fulfilled'`.
     - Execution ids are unique, so the join yields at most one row.
     - An execution that was attached rather than dispatched has no row and carries none of the fields.
   - The change is read-only: no migration and no write path.
   - The mctl-agents side then uses the previous execution's `surface`/`requested_by` as its baseline. That is a separate PR in mctl-agents after this release.

Why this way: the fail-closed decision sits next to the existing intent check, under the same item lock, using the store's established NULL-text meaning of redaction. The fulfil-time recheck is the only place mctl-api can stop a placeholder run after enqueue without trusting the worker.

## Alternatives
- Substitute the latest readable intent when the pinned one is redacted. Rejected: the issue forbids automatic substitution, and it would run work the requester never bound.
- Recheck only in the worker (mctl-agents). Rejected as the sole guard: an old worker image would run on placeholder text. Kept as the first line (via `intent_available`), with fulfil as the backstop.
- Auto-reject the request in the store when the intent is redacted at claim. Rejected: rejection is the holder's act (claim-token fenced). The holder (mctl-agents' dispatcher, #963) rejects it with a typed reason as soon as it sees `intent_available=false`. That is not a silent close: the request records the reason, and no loop or engine run is ever started.

## Platform impact
- Migrations: none. The `intent_id` column already exists, and the check reads `work_item_intents.text`.
- Backward compatibility:
  - The REST create of a readable intent is unchanged.
  - A NULL-text intent changes from 201 to 409. No production intent is NULL yet (no sweeper), so in practice no live caller sees this change.
  - The claim response gains one field, which tolerant decoders ignore.
- Dispatcher behaviour, verified against `orchestrator/temporal/dispatcher.py` on mctl-agents main (1.114.1):
  - Today it rejects on a fulfil refusal only for `TERMINAL_FULFIL_CODES = {state_version_conflict, invalid_transition}`, and **defers** on any other 4xx.
  - An `intent_unavailable` fulfil refusal from an unchanged dispatcher therefore cycles through claim, deliver, fulfil 409 and defer until the accepting loop's `FULFILMENT_WAIT` runs out. The next claim then rejects with the misleading reason `engine_run_ended`.
  - mctlhq/mctl-agents#963 fixes this: it adds `intent_unavailable` to the terminal codes and rejects on `intent_available=false` before any delivery.
- **Rollout order (hard):**
  1. mctl-agents#963 released and running on the exec workers. It is inert against today's API.
  2. This PR is released.
  3. The agents side of #960 follows this release.
- Old-image test (T11) stays, rewritten for the dispatcher's real behaviour: an unknown-code 409 attaches no execution, and the request stays claimed until the lease lapses.
- The condition cannot occur in production until mctl-api#353 ships a sweeper.
- Portal `request_execution` stays disabled; this change does not touch it.
- Resource impact: one indexed primary-key lookup per create, claim and fulfil.
- Risk: a leak of intent text in errors or audit records. Mitigation: only ids appear in errors and audit records, and a test asserts it.
