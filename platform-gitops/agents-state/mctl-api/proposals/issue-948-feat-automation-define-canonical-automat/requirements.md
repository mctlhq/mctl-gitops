# Canonical AutomationDefinition v1 contract: schemas, templates and authorization (contract-only)

## Context

The Automation Control Plane decision (mctlhq/.github#318, outcome `EXTEND_MCTL_API`) and its
implementation epic (mctlhq/.github#322) need a stable, security-reviewed API and authority
contract before anything is built: `au_` storage, Temporal schedules, agent execution or surface
integration. The research report and its `v0` reference schemas are spike evidence. They are not a
production contract. In particular, the Go model and the Temporal proof do not establish
cross-surface principal linkage, delegated authority or action-time enforcement.

This proposal delivers the epic work item `automation-contract` (phase `authority`, owner
`mctl-api`) as contract-only artifacts in `mctl-api`:

- a normative document, `docs/automation-contract.md`;
- versioned JSON Schemas (draft 2020-12) for the create request, the returned definition, the
  patch request, the trigger policies, the `reminder.v1` and `support.diagnostic-followup.v1`
  templates, the run view and the error envelope;
- a pure, store-free Go validation harness, `internal/automation/contract`, with deterministic
  negative contract tests.

The contract is grounded in records that already exist and reuses them:

- `workitem/v1`: `wi_`, `we_`, `cs_` (`docs/work-context-contract.md`, `internal/workitems`).
- `ExecutionRequest` (`xr_`, `internal/workitems/execution_requests.go`) and ADR 0001.
- `ActionApprovalRequest` (`aar_`, `internal/workitems/action_approvals.go`) and its governance
  revalidation (`internal/governance`).
- `SurfaceIdentityLink` (`sil_`, `internal/surfaceid`).
- Delegation grant resolution (`internal/delegation`).
- Agent run scopes, including `support` (`internal/auth/agent_scope.go`).
- The commerce budget ledger (`internal/commerce/budget.go`).

The contract adds no second store, ledger, approval engine or authority engine.

## User stories

- AS the epic owner I WANT a reviewed, versioned AutomationDefinition v1 contract SO THAT `automation-api-store` can start against a fixed target instead of the spike `v0` model.
- AS a security reviewer I WANT machine-checkable schemas with negative tests for spoofing, replay, cross-owner access and unsafe Temporal requests SO THAT I can verify fail-closed behaviour without reading prose alone.
- AS a tenant user on Claude, ChatGPT or Telegram I WANT a reminder that fires once at a local time SO THAT I am notified without granting the platform any standing human approval.
- AS a Support operator I WANT bounded, read-only diagnostic follow-ups SO THAT a support conversation can re-check a tenant at most three times within 24 hours, under the owner's live authority.
- AS an mctl-agents, mctl-telegram or mctl-support maintainer I WANT an explicit interface-ownership crosswalk SO THAT I know which records I consume and which I must never write.

## Acceptance criteria (EARS)

### Artifacts and harness

- WHEN the contract slice is merged THE SYSTEM SHALL contain:
  - `docs/automation-contract.md`;
  - the JSON Schemas under `internal/automation/contract/schema/v1/`, each with a `$id` under
    `https://mctl.ai/schemas/automation/v1/`;
  - a Go package `internal/automation/contract` that embeds them with `//go:embed` and compiles
    them with `github.com/santhosh-tekuri/jsonschema/v6` (the same mechanism as
    `internal/deployanalyze/schema.go`).
- WHEN `go test ./internal/automation/...` runs THE SYSTEM SHALL check every fixture under
  `internal/automation/contract/testdata/{valid,invalid}/`. A valid fixture must pass. An invalid
  fixture must fail with exactly the error code named in its fixture manifest.
- WHILE the contract slice is the only automation code THE SYSTEM SHALL register no new MCP tool,
  REST route, database table, migration, Temporal client call, environment flag or Helm value.
  This leaves `TestNewMCPServer_ToolCount` in `internal/mcp/server_test.go` and
  `internal/openapi/openapi.yaml` unchanged.

### Identity and per-fire records

- THE SYSTEM SHALL specify `AutomationDefinition` (`au_` + UUID) as standing intent only. It is not
  an execution record.
- THE SYSTEM SHALL specify `AutomationRun` as a read-only view over one fire's
  `wi_ -> xr_ -> we_` chain, keyed by the fire's `occurrence_key`.
- WHEN a trigger fires THE SYSTEM SHALL derive
  `occurrence_key = "occ_" + hex(sha256(au_id | definition_version | trigger_kind | occurrence_instant_utc_or_event_delivery_id))[:32]`.
  The per-fire WorkItem uses `external_key = "automation:" + au_id + ":" + occurrence_key`. The
  idempotency key is derived from the `occurrence_key` and is never chosen by a client.
- WHEN two occurrences of one definition overlap THE SYSTEM SHALL give them two different `wi_`
  ids. Each `wi_` keeps the existing invariant of at most one open `we_` per item.
- IF the same occurrence is delivered twice THEN THE SYSTEM SHALL produce the same
  `occurrence_key`, and the harness SHALL classify the second delivery as a replay
  (`automation_occurrence_duplicate`). A replay never creates a second `wi_`.

### Request, definition and patch schemas

- THE SYSTEM SHALL publish three separate schemas, all with `additionalProperties: false`:
  `automation-create-request.v1`, `automation-definition.v1` (the returned resource) and
  `automation-patch.v1`.
- IF a create or patch body contains a server-owned field THEN the harness SHALL reject it with
  `automation_server_owned_field`. The server-owned fields are `id`, `tenant`, `owner_principal`,
  `created_by`, `actor`, `surface`, `origin_client_id`, `version`, `state`, `lifecycle`,
  `provenance`, `created_at`, `updated_at`, `template_binding`, `capability`, `task_queue`,
  `workflow_type`, `namespace` and `signal`.
- IF a body contains an unknown field THEN the harness SHALL reject it with
  `automation_unknown_field`. IF a body is malformed JSON or violates the schema THEN the harness
  SHALL reject it with `automation_invalid`.
- WHEN a definition is updated, paused, resumed or deleted THE SYSTEM SHALL require
  `expected_version` (optimistic compare-and-set). A mismatch is `automation_version_conflict`
  (409).
- WHEN a create request repeats an `idempotency_key` with an identical body THE SYSTEM SHALL return
  the original definition with `replayed: true`. A repeat with a different body is
  `automation_idempotency_key_reused` (409).
- THE SYSTEM SHALL specify these operations as a closed set, each with typed request, response and
  error schemas: `create`, `get`, `list` (with cursor pagination, a `limit` of 1 to 100, and
  filters for `state` and `template` only), `update`, `pause`, `resume`, `delete`, `run` (manual
  fire) and `list_runs`.

### Templates and triggers

- THE SYSTEM SHALL accept only template ids on a server-side allowlist. Initially that is
  `reminder.v1`, plus `support.diagnostic-followup.v1` under the Support constraints below.
- The server SHALL map each allowlisted template to its capability, queue and workflow. IF a
  client names an unknown template, a workflow type, a namespace, a task queue, a signal or any
  raw Temporal control THEN the harness SHALL reject it with `automation_template_not_allowed` or
  `automation_server_owned_field`.
- THE SYSTEM SHALL specify these trigger kinds: `at`, `schedule`, `event` and `dependency`. Only
  `at` is in the MVP gate. The others are schema-valid but answer `automation_trigger_unsupported`
  until a later approved slice enables them.
- WHEN an `at` trigger is given as a local time THE SYSTEM SHALL require an IANA zone name and an
  explicit DST policy:
  - for a nonexistent (spring-forward) local time, `dst_gap` is `shift_forward` or `reject`;
  - for an ambiguous (fall-back) local time, `dst_fold` is `earlier`, `later` or `reject`.
- IF an `at` time resolves into a DST gap or fold and the policy is `reject` THEN the harness SHALL
  reject it with `automation_time_ambiguous`.
- IF an `at` trigger names an unknown zone or an offset-only zone THEN the harness SHALL reject it
  with `automation_invalid`.
- THE SYSTEM SHALL specify these policies with closed enums:
  - overlap: `skip`, `buffer_one`, `allow_all`;
  - catch-up: `none`, `latest_only`, with a bounded window;
  - fanout: `single`;
  - cancellation: `cancel_open_runs`, `let_open_runs_finish`.
- Every Temporal behaviour the contract relies on but has not verified SHALL be marked `UNVERIFIED`
  in the normative document.

### Principal and tenant authority

- WHEN a request arrives from Claude or ChatGPT over OAuth, or from a Telegram AssistantInstall
  relay, THE SYSTEM SHALL specify that the owner principal is resolved server-side through the
  authenticated token or a live `SurfaceIdentityLink` (`surfaceid.Store.Resolve`).
- IF the identity is unknown, unlinked, expired or revoked, or the surface or tenant does not match,
  THEN the contract SHALL require refusal with `automation_identity_unlinked`, which answers 403 on
  every refusal reason. The decision model SHALL never fall back to a default owner.
- IF a request tries to change the owner, names a tenant the caller cannot access, or reads another
  owner's definition in the same tenant THEN the contract SHALL require
  `automation_not_found` (404). The answer SHALL be identical to the one for a definition that
  does not exist, so it gives no existence oracle.
- THE SYSTEM SHALL distinguish the creator (`created_by`) from any delegate actor. A delegate can
  only be selected through an existing delegation grant (`internal/delegation`). It is never
  asserted by a client.

### Authorization checkpoints

- THE SYSTEM SHALL specify three authorization checkpoints:
  - (a) at create and update;
  - (b) at fire time, before the per-fire `wi_` is created;
  - (c) immediately before each externally observable side effect.
- Each checkpoint re-resolves identity, install revision, tenant membership, policy version and
  budget from live sources.
- IF a live authority source cannot be read at any checkpoint THEN the decision SHALL be
  `automation_authority_unavailable` (503) and the fire or side effect SHALL not proceed.
  "Unknown" is never "allowed".
- IF identity or install is revoked or expired between create and fire, or mid-flight before a
  side effect, THEN the contract SHALL require refusal at the next checkpoint with
  `automation_identity_unlinked`.
- IF the policy version pinned at create differs from the live one THEN the contract SHALL require
  `automation_policy_drift`.
- IF a per-run, per-day or per-tenant budget would be exceeded THEN the contract SHALL require
  `automation_budget_exhausted`, using the existing commerce budget ledger.
- WHILE an automation exists THE SYSTEM SHALL never treat its schedule, its creation or its
  `auth_ref` as human approval.
- IF an occurrence needs an action approval THEN it SHALL request a fresh `aar_` for that
  occurrence's own `we_`. Reusing, auto-deciding or consuming an `aar_` that belongs to another
  occurrence SHALL be rejected with `automation_approval_not_reusable`.

### Support constraints

- WHEN a definition uses `support.diagnostic-followup.v1` THE SYSTEM SHALL require all of the
  following, and any violation is `automation_support_constraint`:
  - the tenant owner's authorization;
  - binding to exactly one tenant;
  - the `support` agent scope (read-only);
  - a TTL of at most 24 hours;
  - at most 3 fires.
- IF a Support definition names a delegated actor, an impersonated owner or any write capability
  THEN the contract SHALL require `automation_support_constraint`.
- An `auth_ref` SHALL be validated as an opaque claim that requires independent live authorization
  at every checkpoint. Its presence alone never authorizes anything.

### Transport, delivery and ingress

- THE SYSTEM SHALL define the user-visible `sync_state` as one of:
  - `pending`: desired state is not yet observed in Temporal;
  - `applied`: observed state equals desired state;
  - `failed`: reconciliation refused or exhausted its retries, with a typed reason.
- THE SYSTEM SHALL also define a fail-closed orphan rule: a Temporal schedule with no live `au_` is
  deleted, never adopted.
- THE SYSTEM SHALL define the reconciler's dedupe and backoff, and Telegram delivery outcomes
  (`delivered`, `undeliverable`, `unknown`) as a field of the run view. A delivery outcome never
  re-fires an occurrence.
- IF an `event` trigger names `check_run` or `workflow_run` THEN the harness SHALL reject it with
  `automation_trigger_unsupported`.
- Event ingress SHALL be specified as a signed producer with tenant hydration on the server side,
  using the existing HMAC-verified webhook outbox (`docs/github-events-producer.md`), with a
  replay key per subscriber.

### Versioning and errors

- THE SYSTEM SHALL publish a versioned error vocabulary (`automation-error.v1`). Codes are only
  ever added; an existing code's meaning never changes.
- THE SYSTEM SHALL state that research `v0` documents have no compatibility promise. A `v0`
  document submitted to the harness is rejected as `automation_invalid`.
- THE SYSTEM SHALL define an audit, privacy and secret-redaction boundary:
  - reminder text is at most 2 KiB;
  - reminder text is checked by the existing secret scanner (`internal/secretscan`) and refused on
    a match;
  - reminder text is never copied into audit detail.
- THE SYSTEM SHALL define the MVP gate as `reminder.v1` with an `at` trigger only.
- The normative document SHALL classify every claim as proved source, isolated model, assumed or
  unknown.

### Process

- IF a test or repository CI cannot run THEN the implementer SHALL record the exact blocker in the
  PR description and SHALL NOT report acceptance.

## Out of scope

- `au_` storage, migrations, or any PostgreSQL table.
- Temporal client writes, schedules, workers or reconcilers.
- Real event subscriptions.
- User-facing MCP tools or REST routes.
- Feature flags, Helm or gitops changes, deployment, and any live automation.
- Filing or activating downstream issues. `automation-api-store` and later slices are proposed in
  the normative document for owner review only.
- The delegation policy of mctl-api#901 (separate and unapproved).
- Same-chat push (.github#300, unknown).
- MCP Tasks (mctl-api#284), which is only referenced.
- Any automatic human approval or policy-enrollment bypass.

## Open questions

- **Durable occurrence dedupe after close.** The existing WorkItem `external_key` dedupe only
  matches an *open* item (MCP tool description for `mctl_create_work_item`). A duplicate delivery
  after the first fire's item has closed would therefore not be caught by `external_key` alone.

  This proposal relies on `idempotency_key` replay instead, with the key derived from
  `occurrence_key`. It records the retention of work-item idempotency keys as `assumed` and
  carries it as a required decision for `automation-api-store`. That slice may need a small
  occurrence-claim table.
- **Representation of the Telegram AssistantInstall.** No `AssistantInstall` type exists in this
  repository. Only `surfaceid.SurfaceTelegram` links do. The contract treats install revision as
  an opaque, server-resolved `install_ref` and marks it `unknown` until mctl-telegram defines it.
- **Claude and ChatGPT as surfaces.** `surfaceid.IsSurface` only knows `telegram` and `portal`.
  This proposal treats Claude and ChatGPT callers as direct OAuth principals with
  `origin_client_id`. Neither gets a `SurfaceIdentityLink`. The reviewer should confirm this.
- **Budget owner.** Whether per-day and per-tenant automation budgets reuse commerce `budgets`
  rows or need a new budget class is marked `assumed: commerce ledger` pending owner decision.
- **Spike sources.** The spike schemas in mctlhq/.github could not be fetched in this read-only
  run. The crosswalk to `v0` is described by intent, and the implementer must diff against
  `docs/spikes/automation-control-plane/schemas` when writing the migration note.
