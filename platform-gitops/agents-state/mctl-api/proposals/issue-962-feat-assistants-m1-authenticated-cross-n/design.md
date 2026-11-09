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
- Identity: `command_id TEXT PK ('cmd_' + 26 ASCII alphanumeric characters)`, `execution_id`, `workflow_id`, `run_id`, `tenant`, `owner_principal_id`, `connection_id`, `install_revision`, `provider_ref`, `operation_kind`.
- Binding: `intent_hash`, `approval_ref ('aar_')`, `operation_key`, `sequence BIGINT`, `payload JSONB`, `payload_digest`.
- Lease: `status CHECK IN ('pending','leased','completed','cancelled','expired')`, `command_nonce` (projected as required v1alpha1 command `nonce`), `lease_nonce` (internal), `lease_id` (internal), `lease_epoch BIGINT` (internal), `lease_token` (opaque external `lt_...`), `leased_by`, `lease_expires_at`, `expires_at`.
- Result: `result_digest`, `result JSONB`, `effect_state CHECK IN ('none','permitted','succeeded','failed','not_performed','unknown')`.
- Timestamps: `created_at`, `updated_at`.

Constraints:
- `UNIQUE (tenant, execution_id, operation_key)` gives idempotent enqueue.
- `UNIQUE (execution_id, sequence)` gives ordering.

Supporting tables:
- `bridge_command_transitions`: append-only, ids and digests only.
- `bridge_signal_outbox`: `command_id PK`, `status pending/sent`, `attempts`, `last_error_code`. This is the transactional signal outbox.
- `bridge_write_permits`: `command_id PK`, `operation_key UNIQUE`, `approval_ref`, `fence_ref`, `issued_at`, `lease_epoch`. Its uniqueness prevents duplicate permit records; **at most one visible synthetic effect additionally requires #954's single-use receipt and the fake provider's operation-key dedupe/read-back**.

### 2. Store (`internal/bridge/store.go`)

- `Enqueue(ctx, tx pgx.Tx, EnqueueInput)` takes the caller's transaction, which makes it the transactional outbox. The input struct has no fields for an endpoint URL, a token, raw session data or a workflow id from the caller. `workflow_id` and `run_id` come from the server-created execution record that control code passes in.
- `Claim(ctx, providerRef, principalID, max, leaseTTL)` runs `UPDATE ... WHERE command_id IN (SELECT ... FOR UPDATE SKIP LOCKED)`. The selection is scoped by `provider_ref` and a status/lease-expiry predicate. It rotates the private `lease_nonce`, `lease_id`, `lease_epoch+1` and opaque `lease_token`, and lazily marks commands past `expires_at` as `expired`. The outward claim projection includes the required server-generated command `nonce` (from `command_nonce`) and must strictly validate against #1045 without private lease fields.
- `SubmitResult(ctx, principalID, commandID, ResultInput)` first validates the unchanged #1045 result schema, then locks the row `FOR UPDATE`, verifies the submitted `lease_token`, `execution_id`, `attempt`, `worker_identity` and caller against stored bindings, and makes the internal CAS on current `status='leased'`, `lease_epoch` and private `lease_nonce`. Do NOT add epoch, nonce, tenant, intent hash or operation key to the strict result JSON. In the same transaction it inserts `bridge_signal_outbox`. A replay of the same server-computed digest returns the stored outcome.
- `IssueWritePermit(ctx, ...)` locks the command and calls `workitems.Store.ActionApproval` for the `aar_` with a lock variant. The locked `getActionApproval` path accepts a lock string, which lets the approval row be locked in the same transaction, so a revocation is serialized against the permit. It then calls `WriteFence.Check(ctx, tx, binding)`, an interface to #954's **single canonical** transactional reserve/consume/record-outcome fence; its default `refusingFence` returns `ErrWriteFenceUnavailable` and issues zero permits. The write permit is inserted only after atomic tenant/owner/connection/install-revision/approval/revocation checks, with no second grant store. The approval must be state approved, decided by a human, unexpired and unrevoked, and its `IntentHash` must equal the command's `intent_hash`.
- `Cancel(ctx, tx, commandID)` and `ReadOutcome(ctx, commandID)`. Control code uses `ReadOutcome` to read back before any retry.

### 3. Auth (`internal/auth/bridge_provider.go`)

- `NewBridgeProviderUser(ref)` returns `service:bridge-provider:<ref>`, which holds only `PermissionBridgeProvider = "bridge:provide"`. Its `Identity()` case is added to `principal.go` like `securityProvider`.
- The candidate HTTP bridge credential is a federated OIDC `kind: service` entry (projected ServiceAccount JWT, exact audience `mctl-api-bridge`, pinned issuer + subject + signature/JWKS trust + expiry; `MCTL_BRIDGE_PROVIDERS` JSON `{ref, issuer, subject, audience, tenants[]}`). Configured tenants are only an upper bound; tenant/owner bindings are read from stored commands. Static tokens are **tests-only**. Choosing ZITADEL/Vault as Temporal workload JWT issuer is separate research #2506, and must not silently select this HTTP token's issuer.
- A router middleware `requireBridgeProvider` guards the claim/result/write-permit provider endpoints only. A guard `denyBridgeProviderElsewhere` refuses bridge principals on every other route. It sits next to the existing per-kind gates, so the principal cannot reach DevLoop or Temporal handlers even if a gate is misconfigured.

### 4. Handlers (`internal/api/handlers_bridge.go`)

- Routes: `POST /bridge/commands/claim`, `POST /bridge/commands/{command_id}/result`, `POST /bridge/commands/{command_id}/write-permit`.
- Claim command envelopes and result bodies validate against the pinned **unchanged** #1045 schemas (JSON Schema 2020-12) in `internal/bridge/schema/`, with upstream SHA, byte-hash provenance and failing drift check. The separate write-permit endpoint uses a narrow private request/response model, not unreviewed additions to the v1alpha1 command/result schema.
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

The provider gets no control Temporal address/token or `MCTL_TOKEN`. mctl-api is the sole **privileged control-plane Temporal client** for assistant start/signal/query/list, while trusted workers may poll their own namespace with scoped identities. The enforced frontend auth (mctl-gitops#2456 and #2469) is a recorded deployment gate.

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

## AMEND — normative contract/security mapping after merged #1045 (2026-11-08)

**Wire schema authority:** mctl-agents PR #1045, reviewed head `b230c0f571a64e3ca41da9b270abbbad16ca5187`, merged as `14645f93fd4eb425a3ac5adeae497209431b8342`. Vendor exact unmodified JSON schema bytes with upstream provenance/hash, and test against those fixtures. If wire changes are required, raise a coordinated change across mctl-agents#1044, mctl-telegram#1236 and mctl-api#957 *before* implementation approval.

| Layer | Fields / constraints | Boundary |
|---|---|---|
| Outward command v1alpha1 | `command_id=cmd_`+26 alnum; `schema_version=bridge.mctl.ai/v1alpha1`; `execution_id=we_...`; required `work_item_id=wi_...`, `tenant_ref=tnr_...`, `principal_ref=prr_...`, `order_ref=ordr_...`, `connection_ref=gcn_...`, `kind`, `attempt`, `intent_hash`, `issuer=mctl-api`, `audience=provider:<name>`, `nonce`, `issued_at`, `expires_at`, `ttl_seconds`, `cancel_requested`, `payload`; `aar_` `approval_ref` mandatory for `place_order_fake` or `cancel_order_fake` | `additionalProperties: false`; no source-supplied tenant/workflow ID |
| Leased claim | strict command projection plus opaque `lease_token=lt_...` | `lease_id`, `lease_epoch` and private `lease_nonce` stored only in DB; the separate required command `nonce` is visible in the command envelope |
| Outward result v1alpha1 | required `schema_version`, `command_id`, `execution_id`, `lease_token`, `attempt`, `worker_identity=provider:<name>`, `outcome`, `provider_effect`, `completed_at`; optional `result_ref`, `error_code`, `error_detail` | `additionalProperties: false`; no tenant, `operation_key`, `lease_epoch`, nonce, approval, workflow ID |
| Internal Postgres records | operation key, sequence, tenant/principal/install revision, immutable basket fingerprint, workflow/run IDs, epoch/nonce, audit and result digest | not accepted as caller-controlled schema extensions |

**Identity:** Bridge HTTP workload token and Temporal JWT serve different resources. Pin HTTP `iss`, `aud`, `sub`, key trust, expiry and provider ref; fail closed on unknown issuer, wrong scope, missing token or expired key. No production credential issuance/config without independent security approval. Do not equate the separate ZITADEL vs Vault Temporal spike #2506 with a ready issuer for the bridge. Temporal frontend auth negative proof from #2456/#2469 remains a P1 blocker.

**Write boundary:** #954 owns authoritative atomic `aar_` reserve → consume → recorded result, and real-time membership/connection/install/revocation checks. #962 calls this exact transactional interface; without #954 it fails with `write_fence_unavailable` and zero permits. Issuing a DB permit alone never proves exactly-once synthetic provider I/O. After timeout/crash, check fake-provider effect by stable operation key; if ambiguous, return `unknown` and do not reissue a mutation. `hir_` is never approval. Support cancellation before and after claim without exposing a second effect.

**Release/governance:** dark by default; no automatic approval, implementer, live identity, Temporal server change, public DNS or rollout from the amendment. Separate P1 deployment and P2 OAuth activation approvals remain compulsory under mctl-gitops#2457.
