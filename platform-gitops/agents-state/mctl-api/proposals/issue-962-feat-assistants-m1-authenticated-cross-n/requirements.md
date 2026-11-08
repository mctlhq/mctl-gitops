# Authenticated Glovo bridge in mctl-api: command outbox, leases and result fencing (fake provider only)

## Context

Glovo's first multi-tenant MCP runs only against a fake provider. It needs a safe way to pass work between the trusted `mctl-assistants` control orchestration and the low-trust `mctl-assistants-provider-glovo` worker. Research in mctl-agents#1043 (PR #1045, not yet merged) selected an API bridge over Temporal Nexus, because the OSS Temporal frontend has no enforced client authentication and the Nexus endpoint caller restrictions are unverified. This proposal adds that bridge to mctl-api:

- a durable Postgres command outbox;
- a machine-authenticated, provider-only claim endpoint with short leases;
- an exactly-once, fenced result callback.

mctl-api stays the only Temporal client, and the provider and the public MCP facade get no Temporal privilege.

This is an implementation proposal only. It ships the code dark: the feature is disabled by default, no provider credential is issued, and nothing is deployed or consumed in production. Any synthetic basket mutation stays behind two checks: the canonical human-approved `aar_` receipt and the mctl-api#954 final physical-write fence, evaluated atomically against revocation. No real Glovo API, order, checkout or payment is in scope.

## User stories

- AS the mctl-assistants control orchestration (inside mctl-api) I WANT to enqueue a fully server-derived provider command in the same transaction as my state change SO THAT commands are neither lost nor invented by a client.
- AS the Glovo fake-provider worker I WANT to claim only commands scoped to me under a short lease, and submit one bound result, SO THAT I can do my job without any control-plane privilege.
- AS a platform operator I WANT every claim, result, refusal and expiry audited (redacted) and traced SO THAT I can reconstruct what the provider did and why something was refused.
- AS a tenant owner I WANT a command for my tenant to be unclaimable and unsatisfiable by anyone else's principal, membership or lease SO THAT another tenant can never cause effects in my basket.
- AS a security reviewer I WANT the feature to ship disabled, with no credentials issued, SO THAT merging the code authorizes nothing.

## Acceptance criteria (EARS)

### Enablement and authentication
- WHILE `MCTL_BRIDGE_ENABLED` is unset or not `true` THE SYSTEM SHALL answer every `/api/v1/bridge/*` route with 404 `bridge_disabled`, create no command, and change no outbox row.
- WHEN a request reaches `POST /api/v1/bridge/commands/claim` or `POST /api/v1/bridge/commands/{command_id}/result` THE SYSTEM SHALL accept it only from a bridge-provider principal: a `service:bridge-provider:<ref>` principal configured in `MCTL_BRIDGE_PROVIDERS`, with the expected audience. Every other caller gets 403 `bridge_principal_required` and zero mutation. That includes humans, admins, agents, surfaces, CI, `MCTL_TOKEN` service users and other service principals.
- IF a bridge-provider principal calls any non-bridge route (DevLoop, work items, operations, Temporal-backed handlers, MCP) THEN THE SYSTEM SHALL refuse it with 403 and make no Temporal call.
- THE SYSTEM SHALL take the tenant, principal, connection and install revision only from the stored command row. It shall never take them from a provider header, a query parameter or the request body.

### Command creation (control side)
- WHEN trusted control code enqueues a command THE SYSTEM SHALL do it inside the caller's Postgres transaction. The server derives and stores: `command_id` (`brc_` prefix), `execution_id`, tenant, owner principal, connection id, install revision, provider ref, operation kind, `intent_hash`, `approval_ref` (`aar_`), `operation_key`, `nonce`, `expires_at` and a monotonic per-execution `sequence`. The status starts as `pending`.
- IF an enqueue request carries an endpoint URL, a user token, raw session data, a client-chosen tenant or a model-controlled workflow id THEN THE SYSTEM SHALL reject it at validation and insert nothing.
- WHEN a second enqueue uses an `operation_key` that is already stored for the same tenant and execution THE SYSTEM SHALL return the existing command and not create a second one.
- THE SYSTEM SHALL validate the command payload against the pinned `command.schema.json` (JSON Schema 2020-12) before it is inserted.

### Claim and lease
- WHEN a bridge provider claims THE SYSTEM SHALL, inside one transaction (`FOR UPDATE SKIP LOCKED`), lease at most `max` (bounded, default 1) commands that meet all of these:
  - addressed to that provider ref;
  - `pending`, or `leased` with an expired lease;
  - not past `expires_at`.

  Each lease stamps a fresh `lease_id`, `lease_expires_at` (short, default 30s), an incremented `lease_epoch` and a fresh `nonce`.
- THE SYSTEM SHALL return only the leased commands. There is no list, read or search route for commands.
- WHEN a lease expires without a valid result THE SYSTEM SHALL let the command be reclaimed under a higher `lease_epoch`. A result bound to an older epoch is then refused.
- WHEN a command passes `expires_at` while it is not completed THE SYSTEM SHALL move it to `expired` and refuse any later claim or result.

### Result callback and fencing
- WHEN a provider submits a result THE SYSTEM SHALL accept it only if, under the row lock:
  - the caller's principal matches the leasing principal;
  - `lease_id`, `lease_epoch` and `nonce` match the current lease;
  - the lease and the command are both unexpired;
  - `intent_hash`, `operation_key`, tenant/owner and `sequence` in the signed body match the command;
  - the body validates against the pinned `result.schema.json`.

  Only then does the command move from `leased` to `completed`, in a single CAS.
- IF any of those checks fail THEN THE SYSTEM SHALL refuse with a typed 409 or 422 code: `lease_stale`, `nonce_mismatch`, `command_expired`, `intent_mismatch`, `owner_mismatch`, `order_mismatch` or `schema_invalid`. It makes zero changes to the row and sends no signal.
- WHEN an identical result (same `result_digest`) is submitted again for a completed command THE SYSTEM SHALL return the stored outcome with `replayed: true`, and send no second signal.
- IF a result with a different digest is submitted for a completed command THEN THE SYSTEM SHALL refuse it with 409 `result_conflict`.
- WHEN a result is accepted THE SYSTEM SHALL commit it and enqueue a signal record in the same transaction. It then signals only the server-created workflow whose id and run id are stored on the command. No caller supplies a workflow id.
- IF the signal fails or its outcome is unknown THEN THE SYSTEM SHALL keep the signal record pending and retry it idempotently, keyed by `command_id`. It shall never re-run the command or report success that was not confirmed.

### Effect authorization (fake provider)
- WHEN a provider asks to perform a synthetic basket mutation (`POST /api/v1/bridge/commands/{command_id}/write-permit`) THE SYSTEM SHALL issue a permit only if, in one transaction that locks the command and the referenced `aar_`:
  - the `aar_` is approved by a human, unexpired, unrevoked and bound to the command's `intent_hash`;
  - the mctl-api#954 physical-write fence passes;
  - the provider holds the current lease.
- IF the #954 fence is not available in the build THEN THE SYSTEM SHALL refuse every write permit with 503 `write_fence_unavailable`, fail closed.
- IF the approval is revoked at any point before the permit is issued, including after the command was signed or claimed THEN THE SYSTEM SHALL refuse the permit, and the command can only be completed with a `not_performed` outcome.
- THE SYSTEM SHALL never treat a signed dispatch, a cached claim or an `hir_` reference as authorization for I/O.
- THE SYSTEM SHALL record at most one visible synthetic effect per `operation_key`. A retry must first read back the stored outcome. An unknown effect is recorded as `unknown`, never as `succeeded`.

### Cancellation
- WHEN control code cancels a command THE SYSTEM SHALL move `pending` or `leased` to `cancelled` with CAS. A result that arrives after the cancel is refused with `command_cancelled`, and no write permit is issued after cancel.

### Isolation, limits and observability
- WHILE the feature is enabled THE SYSTEM SHALL apply a bridge rate budget that is separate from the global limiter. The budget is per provider principal.
- THE SYSTEM SHALL emit an OTel span for every enqueue, claim, result, permit and signal. It shall write audit entries that never contain payload bodies, nonces, lease ids or tokens; only ids and digests are recorded.
- IF the caller is in any of these situations THEN THE SYSTEM SHALL fail closed with zero extra mutation:
  - a different team tenant;
  - a second owner in the same tenant;
  - a revoked membership;
  - an unselected tenant;
  - the wrong audience;
  - the wrong lease;
  - the wrong receipt.

## Out of scope

- Any Kubernetes, Temporal, DNS, TLS or Cloudflare resource creation; any P1 or P2 release; issuing provider credentials; production outbox consumption.
- Implementing Temporal frontend JWT/TLS auth (mctl-gitops#2456, #2469). It is a deployment prerequisite, not part of this change.
- The mctl-assistants control workflow (mctl-agents#1044) and the fake worker (mctl-telegram#1236).
- Real Glovo API calls, order placement, checkout and payment.
- Implementing the #954 physical-write fence itself. This proposal only calls it, and fails closed while it is absent.

## Open questions

- The pinned schemas `mctl-agents/docs/spikes/1043/{command,result}.schema.json` live in an unmerged PR (mctl-agents#1045) and were not readable from this run. Proposal: vendor them into `internal/bridge/schema/` with a recorded upstream commit and sha256, and add a CI check that compares digests. Field names in this proposal follow the issue text and may need renaming to match.
- The mctl-api#954 physical-write fence does not exist in this clone (no matching symbol). Proposal: an interface `WriteFence` with a default implementation that always refuses, until #954 lands.
- The provider workload identity mechanism is not decided. Proposal: a Kubernetes projected ServiceAccount token, verified as a federated OIDC `kind=service` issuer (`MCTL_OIDC_PROVIDERS`), with audience `mctl-api-bridge`. A static-token fallback modeled on `MCTL_SECURITY_PROVIDER_TOKENS` is allowed for tests only.
- "Signed/bound result": this proposal binds the result by the lease nonce plus the request authentication, and records a `result_digest`. A detached provider signature (for example an Ed25519 key per provider) is left optional until reviewers decide whether it is required.
- The namespace and service names `mctl-assistants` and `mctl-assistants-provider-glovo` do not exist yet in mctl-gitops (see design.md, Deployed state checked). They are used here as names only.
