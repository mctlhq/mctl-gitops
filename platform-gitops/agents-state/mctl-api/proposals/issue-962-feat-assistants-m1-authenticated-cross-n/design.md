# Design: issue-962-feat-assistants-m1-authenticated-cross-n

## Current state

- **Temporal client.** mctl-api is already the Temporal client for DevLoop.
  - `internal/temporalclient/client.go` (`New`, `StartDevLoopWorkflow`, `SignalApprove`, `SignalAbandon`, `SignalHumanInputResponse`, `DescribeDevLoopRun`) is wrapped by the `DevLoopClient` interface in `internal/api/interfaces.go`.
  - It is wired in `cmd/api/main.go` only when `TEMPORAL_ADDRESS` is set, using `TEMPORAL_NAMESPACE`.
  - Handlers live in `internal/api/handlers_dev_loop.go`, with routes at `internal/api/router.go` (`/agents/dev-loop/...`).
  - There is a single namespace and no bridge or outbox concept.
- **Claim/CAS precedent.** `internal/workitems/execution_requests.go` defines a `work_item_execution_requests` table with a state CHECK (`pending`, `claimed`, `fulfilled`, `rejected`) and partial unique indexes on open states. It has `ClaimExecutionRequest` and `RejectExecutionRequest`, and uses `FOR UPDATE` row locks. This is the pattern the outbox reuses.
- **Additive schema precedent.** `internal/commerce/store.go` applies an idempotent `commerceSchema` (`CREATE TABLE IF NOT EXISTS ...`, with named CHECKs added separately) on every start, through `pgshared` pools. There is no migrations directory. Schema is applied in code.
- **Approvals.** `aar_` action approvals live in `internal/workitems/action_approvals.go` (`IntentHash`, `ActionApproval`, `effectiveState`). They are spent through `prepareApprovalGrant`, `bindApprovalGrant` and `spendApprovalGrant` in `internal/api/handlers_approval_grant.go`, with binding checks in `internal/api/approval_binding.go`.
- **Service principals.** `internal/auth/principal.go` defines `KindService` and per-role user discriminators. `internal/auth/security_provider.go` is a close precedent for a narrow machine principal: `service:security-provider:<ref>`, configured by `SECURITY_PROVIDERS`, with tokens in `MCTL_SECURITY_PROVIDER_TOKENS` checked by constant-time compare, holding a single permission. `internal/auth/federation_config.go` already accepts `MCTL_OIDC_PROVIDERS` entries with `kind: service`.
- **Missing pieces.**
  - No physical-write fence (mctl-api#954): grepping for `PhysicalWrite`, `#954` and `final fence` finds nothing.
  - No bridge, Glovo or assistants code. The only `assistant` hits are the catalog tests `internal/agentregistry/assistant_catalog_test.go` and `internal/api/handlers_assistant_catalog_test.go`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/`: tenants are `admins`, `karabu`, `labs` and `namax66`. `services/admins/` lists the `mctl-agents-worker*`, `mctl-design`, `mctl-docs`, `mctl-support`, `mctl-web` and `umami` services. There is no `mctl-assistants` or `mctl-assistants-provider-glovo` service anywhere (a grep for `assistants` or `glovo` under `services/` and `tenants/` returned nothing).
- `$MCTL_GITOPS_ROOT/tenants/`: `admins`, `commerce-proof`, `erpact`, `karabu`, `labs`, `mctl`, `namax66`. None is assistants-specific.
- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/networkpolicy.yaml`: Temporal ingress allows the `mctl-api` namespace, the `admins` agents-worker pods and `labs-kuptsi-app`, plus traefik on 8080 and monitoring on 9090. So today network policy, not client auth, is the only Temporal gate. This is consistent with the issue.
- mctl-api's own deployed values were not located under `services/`. Whether `TEMPORAL_ADDRESS` or `TEMPORAL_NAMESPACE` is set in production was **not observed**. mctl MCP read tools were not used in this run.

## Proposed solution

Add a new package `internal/bridge` plus thin handlers. Everything ships behind `MCTL_BRIDGE_ENABLED=false`.

### 1. Schema (additive, in `bridgeSchema`, applied like `commerceSchema`)

`bridge_commands` columns:
- Identity: `command_id TEXT PK ('brc_'...)`, `execution_id`, `workflow_id`, `run_id`, `tenant`, `owner_principal_id`, `connection_id`, `install_revision`, `provider_ref`, `operation_kind`.
- Binding: `intent_hash`, `approval_ref ('aar_')`, `operation_key`, `sequence BIGINT`, `payload JSONB`, `payload_digest`.
- Lease: `status CHECK IN ('pending','leased','completed','cancelled','expired')`, `nonce`, `lease_id`, `lease_epoch BIGINT`, `leased_by`, `lease_expires_at`, `expires_at`.
- Result: `result_digest`, `result JSONB`, `effect_state CHECK IN ('none','permitted','succeeded','failed','not_performed','unknown')`.
- Timestamps: `created_at`, `updated_at`.

Constraints:
- `UNIQUE (tenant, execution_id, operation_key)` gives idempotent enqueue.
- `UNIQUE (execution_id, sequence)` gives ordering.

Supporting tables:
- `bridge_command_transitions`: append-only, ids and digests only.
- `bridge_signal_outbox`: `command_id PK`, `status pending/sent`, `attempts`, `last_error_code`. This is the transactional signal outbox.
- `bridge_write_permits`: `command_id PK`, `operation_key UNIQUE`, `approval_ref`, `fence_ref`, `issued_at`, `lease_epoch`. Its uniqueness enforces at most one visible effect.

### 2. Store (`internal/bridge/store.go`)

- `Enqueue(ctx, tx pgx.Tx, EnqueueInput)` takes the caller's transaction, which makes it the transactional outbox. The input struct has no fields for an endpoint URL, a token, raw session data or a workflow id from the caller. `workflow_id` and `run_id` come from the server-created execution record that control code passes in.
- `Claim(ctx, providerRef, principalID, max, leaseTTL)` runs `UPDATE ... WHERE command_id IN (SELECT ... FOR UPDATE SKIP LOCKED)`. The selection is scoped by `provider_ref` and a status/lease-expiry predicate. It rotates `nonce`, `lease_id` and `lease_epoch+1`, and lazily marks commands past `expires_at` as `expired`.
- `SubmitResult(ctx, principalID, commandID, ResultInput)` locks the row `FOR UPDATE`, runs ordered checks (each with a typed error), and then makes a CAS on `status='leased' AND lease_epoch=$n AND nonce=$m`. In the same transaction it inserts `bridge_signal_outbox`. A replay of the same digest returns the stored outcome.
- `IssueWritePermit(ctx, ...)` locks the command and calls `workitems.Store.ActionApproval` for the `aar_` with a lock variant. The locked `getActionApproval` path accepts a lock string, which lets the approval row be locked in the same transaction, so a revocation is serialized against the permit. It then calls `WriteFence.Check(ctx, tx, binding)`, an interface for #954 whose default `refusingFence` returns `ErrWriteFenceUnavailable`, and inserts `bridge_write_permits`. The approval must be state approved, decided by a human, unexpired and unrevoked, and its `IntentHash` must equal the command's `intent_hash`.
- `Cancel(ctx, tx, commandID)` and `ReadOutcome(ctx, commandID)`. Control code uses `ReadOutcome` to read back before any retry.

### 3. Auth (`internal/auth/bridge_provider.go`)

- `NewBridgeProviderUser(ref)` returns `service:bridge-provider:<ref>`, which holds only `PermissionBridgeProvider = "bridge:provide"`. Its `Identity()` case is added to `principal.go` like `securityProvider`.
- The primary credential is a federated OIDC `kind: service` entry (a projected SA token, audience `mctl-api-bridge`, subject pinned per provider in `MCTL_BRIDGE_PROVIDERS` JSON: `{ref, issuer, subject, audience, tenants[]}`). Configured tenants are an upper bound. The tenant on each command is still taken from the row.
- A router middleware `requireBridgeProvider` guards `/api/v1/bridge/*`. A guard `denyBridgeProviderElsewhere` refuses bridge principals on every other route. It sits next to the existing per-kind gates, so the principal cannot reach DevLoop or Temporal handlers even if a gate is misconfigured.

### 4. Handlers (`internal/api/handlers_bridge.go`)

- Routes: `POST /bridge/commands/claim`, `POST /bridge/commands/{command_id}/result`, `POST /bridge/commands/{command_id}/write-permit`.
- Each handler validates against the pinned schemas in `internal/bridge/schema/` with a JSON Schema 2020-12 validator (`santhosh-tekuri/jsonschema/v6`, if it is not already in `go.mod`).
- Responses use `writeError` / `writeJSON` with typed codes.
- A dedicated `httprate` limiter is keyed per provider principal.
- OTel spans are named `bridge.claim`, `bridge.result`, `bridge.permit` and `bridge.signal`.
- Audit uses the existing audit writer, with redacted params (ids and digests only).

### 5. Signal dispatcher (`internal/bridge/dispatcher.go`)

- A background loop (leader-safe through `FOR UPDATE SKIP LOCKED` on `bridge_signal_outbox`) calls a new `BridgeSignaler` interface method, `SignalBridgeResult(ctx, workflowID, runID, payload)`.
- `*temporalclient.Client` implements it with `SignalWorkflow`, signal name `bridge-result`, carrying `command_id` and `result_digest`, so the workflow can dedupe.
- It signals only the stored `workflow_id`/`run_id`. A `not found` result is recorded as terminal `unknown`, not as success. A transient error is retried with backoff.
- It runs only when the feature is enabled and a Temporal client exists.

### 6. No new Temporal surface for providers

The provider gets no Temporal address, no namespace and no `MCTL_TOKEN`. mctl-api remains the sole client. The enforced frontend auth (mctl-gitops#2456 and #2469) is a recorded deployment gate.

## Alternatives

- **Temporal Nexus endpoints for cross-namespace dispatch.** Dropped for now. The #1043 research reports that OSS 1.31.0 caller restrictions and the stock authorizer are unverified, and the frontend enforces no client auth. A provider holding a Temporal connection would be the privilege this issue forbids.
- **Provider polls Temporal task queues directly as a worker in the control namespace.** Dropped. It gives a low-trust workload gRPC access to the control namespace, and with no frontend auth that means access to DevLoop.
- **Reuse `work_item_execution_requests` as the queue.** Dropped. That table models user-requested executions (`pending`/`claimed`/`fulfilled`/`rejected`) with no lease epoch, nonce, expiry, write permit or per-provider scoping. Overloading it would weaken both contracts. Its claim/CAS pattern is reused instead.
- **Message broker (NATS or Redis streams).** Dropped. It is a new infrastructure dependency (out of scope), and it loses transactional atomicity with control state and with `aar_` revocation.

## Platform impact

- **Migrations.** Additive `CREATE TABLE IF NOT EXISTS` only, applied at start. Unused tables are harmless. Nothing existing is altered.
- **Backward compatibility.** New routes return 404 while the feature is disabled. The new principal kind is unreachable without `MCTL_BRIDGE_PROVIDERS`, which is not set by this change. The MCP tool count is unchanged: no MCP tools are added, so the `server_test.go` count stays the same.
- **Resources.** When disabled, the only cost is the idle tables. When enabled, there is one dispatcher goroutine, small indexed tables, and the bounded claim batch.
- **Risks and mitigations.**
  - Cross-tenant claim: claims are scoped by `provider_ref` and the tenant comes from the row, never the request. A negative test matrix covers it.
  - Stale or replayed result: lease epoch, nonce rotation and CAS. A same-digest replay is a no-op, a different digest is a conflict.
  - Revoke races: the `aar_` row is locked together with the permit insert.
  - Double effect: `operation_key` is unique on permits, and an unknown outcome is recorded as `unknown`.
  - Signal loss: the transactional signal outbox is retried idempotently.
  - #954 absent: the refusing fence makes the feature unable to authorize writes.
  - Schema drift with #1043: the vendored digest is checked in CI.
  - Deploying before Temporal auth: release gate in mctl-gitops#2457, and no credentials issued.
