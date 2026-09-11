# Canonical WorkItem and cross-surface work-state contract

## Context

mctl now has several interaction surfaces (Telegram via `mctl-telegram`,
ChatGPT/Claude via the MCP endpoint at `POST /mcp`, the CLI/REST API, and the
web portal), but no resource that durably owns "the piece of work a human asked
for". What exists today is execution bookkeeping owned by the engines that ran
it: `agent_executions` (per-step Temporal/Argo records, `internal/agentregistry/store.go`),
`audit.Entry` (append-only action log, `internal/audit/logger.go`), `alerts.Alert`
(incident records, `internal/alerts/types.go`), and the live Temporal
`DevLoopWorkflow` reachable only through `GET /api/v1/agents/dev-loop/{workflow_id}`
(`internal/api/handlers_dev_loop.go`). None of these can answer "what is this
person working on, where did it pause, and may this caller resume it" — so every
surface is forced to keep that state locally, which is exactly the parallel
conversation database the parent roadmap wants to avoid.

This proposal defines mctl-api as the system of record for a new canonical
`WorkItem` resource plus its correlated executions, immutable `ContextSnapshot`
records, pending approvals and surface references. The architectural rule is that
surfaces are adapters/views: they may hold rendering and transcript state, but the
durable work state, lifecycle, identity/access policy and correlation IDs live in
mctl-api behind a versioned contract that adapters and `mctl-agents` consume.

## User stories

- AS a platform user starting work in Telegram I WANT the work to be addressable
  by a stable ID SO THAT I can continue it later from ChatGPT, the CLI or the
  portal without re-explaining it.
- AS a platform user I WANT to see the current state of my work item (active,
  waiting on me, waiting on approval, completed) SO THAT I know whether anything
  is expected of me.
- AS a platform user I WANT to resume or retry work SO THAT a failed or paused
  execution does not force me to open a new request from scratch.
- AS a surface adapter author (`mctl-telegram`, portal, CLI) I WANT a versioned
  REST/JSON contract with explicit correlation IDs SO THAT I can build a view of
  work state without owning it or storing transcripts.
- AS an `mctl-agents` orchestrator step I WANT to attach an execution and an
  immutable context snapshot to a work item SO THAT "which run produced this, and
  what context did it see" survives Argo's TTL garbage collection.
- AS a platform admin I WANT actor identity and tenant access re-evaluated on
  every surface transition SO THAT a Telegram chat ID can never inherit a
  different principal's authority.
- AS a platform admin I WANT idempotent writes and explicit optimistic
  concurrency SO THAT two surfaces acting at once cannot silently clobber work
  state.
- AS a data owner I WANT surface references and user intents to be bounded,
  secret-scanned and retention-limited SO THAT no raw chat transcript becomes the
  canonical persistence model.

## Acceptance criteria (EARS)

Resource and ownership

- WHEN an authenticated caller opens work from any surface THE SYSTEM SHALL
  create a `WorkItem` row in mctl-api's own PostgreSQL store (new
  `internal/workitems` package) and return a stable `work_item_id` of the form
  `wi_<uuid>`.
- WHILE a `WorkItem` exists THE SYSTEM SHALL treat mctl-api as its single source
  of truth and SHALL NOT require any surface-local database to reconstruct
  lifecycle state, access policy, correlated executions or pending approvals.
- WHEN any work-state payload is returned THE SYSTEM SHALL include a
  `schema_version` field with the value `workitem/v1`.
- WHEN a surface needs engine detail beyond the contract THE SYSTEM SHALL expose
  it only by correlation reference (engine + engine_ref), never by copying engine
  state into the `WorkItem` row.

Correlation IDs

- WHEN an execution is attached to a work item THE SYSTEM SHALL record
  `(engine, engine_ref)` — for example `("temporal", "dev-loop-mctlhq-mctl-api-227")`
  or `("argo", "<argo_workflow_name>")` — and SHALL make that tuple joinable to
  `agent_executions.temporal_workflow_id` / `agent_executions.argo_workflow_name`
  and to `audit.Entry.WorkflowName` without an FK across stores.
- WHEN a context snapshot is appended THE SYSTEM SHALL assign
  `context_snapshot_id` = `cs_<uuid>` together with a monotonically increasing
  `seq` that is unique per `(work_item_id, execution_id)`.
- WHEN a surface reference is correlated THE SYSTEM SHALL key it on
  `(work_item_id, surface, external_id)` and SHALL reject a second work item
  claiming the same `(surface, external_id)` pair while both are non-terminal.
- IF a create request carries an `external_key` (for example a GitHub issue URL)
  that already identifies a non-terminal work item in the same tenant THEN THE
  SYSTEM SHALL return that existing work item instead of creating a second one.

Lifecycle

- WHEN a work item is created THE SYSTEM SHALL set its state to `active`.
- WHILE a work item is in a non-terminal state (`active`, `waiting`) THE SYSTEM
  SHALL accept intent appends, execution attachments, snapshot appends, approval
  decisions and resume requests.
- WHEN a runtime step needs human input or approval THE SYSTEM SHALL set the
  state to `waiting` and SHALL record a `waiting_reason` of `input` or `approval`.
- WHEN work is resumed THE SYSTEM SHALL move a `waiting` item back to `active`,
  SHALL record a `resumed` lifecycle event, and SHALL NOT introduce a distinct
  persisted `resumed` state.
- WHEN work is finished, replaced or retired THE SYSTEM SHALL move it to exactly
  one terminal state of `completed`, `superseded` or `archived`.
- IF a transition is requested that is not in the documented transition table
  THEN THE SYSTEM SHALL reject it with HTTP 409 and SHALL leave the stored state
  unchanged.
- WHEN a work item is listed without an explicit state filter THE SYSTEM SHALL
  default to the virtual filter `open` (any non-terminal state), mirroring
  `alerts.StatusActive`.

Executions and immutable snapshots

- WHEN a second execution is attached to the same work item THE SYSTEM SHALL keep
  every earlier execution row and every earlier `ContextSnapshot` byte-identical.
- WHILE any `ContextSnapshot` row exists THE SYSTEM SHALL expose no API or store
  method that updates or deletes it (append-only; `snapshot_json` plus a
  `content_hash` over it).
- IF an execution is attached while another execution of the same work item is
  still non-terminal THEN THE SYSTEM SHALL reject the attach with HTTP 409 and
  SHALL return the live execution's identifiers.
- WHEN a resume creates a new execution THE SYSTEM SHALL set
  `resumed_from_execution_id` to the execution being continued and SHALL start a
  new snapshot `seq` sequence for the new execution.

Durable vs surface-local state

- WHILE storing user intent THE SYSTEM SHALL persist only a bounded, normalized
  intent record (max 8 KiB of text plus structured parameters) and SHALL NOT
  require or accept a full chat transcript as the canonical record.
- WHEN intent text is submitted THE SYSTEM SHALL run `secretscan.Scan` over it
  and SHALL reject the append with HTTP 400 when a secret pattern matches, the
  same gate `handlers_openclaw.go` and `handlers_platform_skills.go` already use.
- WHILE a surface holds message formatting, typing state, scroll position, retry
  buffers or raw transcripts THE SYSTEM SHALL treat all of it as surface-local
  and SHALL NOT accept it as part of the durable contract.

Identity, authorization and approvals

- WHEN any work-item request is served THE SYSTEM SHALL derive the acting
  principal solely from `auth.UserFromContext` (GitHub PAT, Dex JWT, OAuth JWT or
  the service principal) and SHALL NOT accept a caller-supplied actor field.
- WHEN a request touches a work item THE SYSTEM SHALL re-evaluate authorization
  on that request using `user.IsAdmin()` / `user.HasTenantAccess(tenant)` and
  SHALL NOT rely on any authorization decision cached at creation time; because
  every surface transition is a new authenticated request, this re-evaluation is
  structural.
- IF a work item's `visibility` is `private` THEN THE SYSTEM SHALL restrict
  non-admin access to the owning principal, and IF it is `tenant` THEN THE SYSTEM
  SHALL allow every principal with access to the owning tenant.
- WHEN a surface-native identity (for example a Telegram user ID or an MCP client
  ID) is presented THE SYSTEM SHALL resolve it to a principal only through an
  explicit `surface_identity_links` binding created by an authenticated call from
  that principal, and SHALL NOT treat a deployment allowlist such as
  `telegram_owner_ids` as proof of identity.
- WHEN a pending approval is recorded THE SYSTEM SHALL store its kind, state
  (`pending`/`granted`/`denied`/`expired`), optional expiry, and the engine signal
  target needed to project the decision.
- WHEN an approval decision is submitted THE SYSTEM SHALL take the decider from
  the authenticated caller only, SHALL reject a request that carries an explicit
  different decider with HTTP 400, and SHALL mark the approval `granted` only
  after the engine signal (for example `SignalApprove`) succeeds — mirroring
  `ApproveDevLoopWorkflow`.
- WHILE an engine owns a runtime approval gate THE SYSTEM SHALL treat the
  work-item approval row as the durable request/record and SHALL NOT bypass the
  engine's own policy gate.
- WHEN the service principal (`auth.User.IsService`) calls THE SYSTEM SHALL allow
  it to attach executions, snapshots and approval requests, and SHALL forbid it
  from recording an approval decision on a human's behalf.

Concurrency and idempotency

- WHEN a mutating request carries an `Idempotency-Key` THE SYSTEM SHALL deduplicate
  it — per `(tenant, idempotency_key)` for create, per
  `(work_item_id, idempotency_key)` for intents, executions, snapshots, approvals
  and resume — and SHALL return the previously created entity with HTTP 200
  instead of creating a duplicate.
- WHEN a state-changing request is served THE SYSTEM SHALL require
  `expected_state_version` (or the equivalent `If-Match` header), SHALL increment
  `state_version` on success, and IF the supplied version does not match the
  stored one THEN THE SYSTEM SHALL respond 409 with the current state and version.
- WHILE mutating one work item THE SYSTEM SHALL serialize the read-modify-write
  inside a single transaction guarded by
  `pg_advisory_xact_lock(hashtext('workitem:' || id))`, the pattern
  `agentregistry.promote` already uses.
- WHEN two surfaces submit the same logical action concurrently THE SYSTEM SHALL
  ensure exactly one of them takes effect and the other observes either the
  idempotent replay or a 409.

Retention and privacy

- WHILE storing a surface reference THE SYSTEM SHALL persist only surface kind,
  external IDs needed for reply routing, the linked principal, and first/last seen
  timestamps.
- WHEN audit entries are written for work-item operations THE SYSTEM SHALL include
  the `work_item_id` and SHALL NOT include intent text or surface external IDs in
  `audit.Entry.Parameters`.
- WHEN the retention sweeper runs THE SYSTEM SHALL delete intent text and surface
  references older than `WORKITEM_SURFACE_RETENTION_DAYS` (default 90) while
  retaining the work item, its lifecycle history and its execution/snapshot
  correlations, and SHALL delete terminal work items older than
  `WORKITEM_RETENTION_DAYS` (default 365).

Availability and configuration

- IF the work-items store is not configured (`WORK_ITEMS_DB_URL` and
  `AUDIT_DB_URL` both unset, `WORK_ITEMS_DISABLED` set, or init failed) THEN THE
  SYSTEM SHALL answer every
  `/api/v1/work-items*` route with HTTP 503 and SHALL log a startup warning naming
  those routes, exactly as the `DomainStore == nil` branch in `router.go` does.
- WHEN the contract changes THE SYSTEM SHALL publish it in
  `internal/openapi/openapi.yaml` and in `docs/work-context-contract.md` under the
  `workitem/v1` version label, and SHALL introduce breaking changes only as a new
  version label.

## Out of scope

- Implementing the Telegram, ChatGPT, CLI or portal adapters themselves; this
  proposal ships the contract, the store and the REST surface plus documentation
  for adapter authors.
- MCP tool wrappers for work items (`mctl_*` tools). They are a follow-up: adding
  tools forces coordinated updates to `internal/mcp/server_test.go`
  (`TestNewMCPServer_ToolCount`) and `internal/mcp/annotations_test.go`
  (`recordedHints`), and the REST + OpenAPI contract is what adapters and
  `mctl-agents` need first.
- Synchronizing messages between surfaces, push/fan-out notification delivery, or
  any real-time subscription mechanism.
- Portal UX and visual design.
- Changing Temporal `DevLoopWorkflow` or Argo workflow semantics, replacing the
  gitops `.status.yaml` proposal flow, or moving the runtime approval gate out of
  the engine.
- Migrating existing `agent_executions`, `alerts` or `audit` rows into work items;
  the contract only defines how to correlate to them going forward.
- Storing model conversation context or prompt history as a first-class resource.

## Open questions

- How a Telegram user proves ownership of a principal: an out-of-band challenge
  like the DNS TXT flow in `internal/domains/verify.go`, a one-time deep link
  minted by an authenticated API call, or gitops-declared `telegram_owner_ids`
  promoted to an identity binding. Assumed for now: an authenticated
  `POST /api/v1/work-items/surface-identities` call from the principal, with
  `telegram_owner_ids` remaining only a deployment allowlist.
- Whether work items get their own database (`WORK_ITEMS_DB_URL`) in production or
  share the audit database. Assumed: own env var with `AUDIT_DB_URL` fallback,
  matching alerts/domains/agent-registry.
- Whether `mctl-agents` writes executions/snapshots with the existing static
  service token or a new scoped credential. Assumed: the existing service
  principal, with the "no approval decisions" restriction above.
- Whether `superseded` needs a pointer to the superseding work item. Assumed yes:
  a nullable `superseded_by` column.
- Whether a work item may span multiple tenants (for example a platform-wide
  incident). Assumed no: exactly one owning tenant, matching `alerts.Alert`.
- Whether snapshots need a size cap distinct from the intent cap. Assumed 256 KiB
  per snapshot with a per-work-item soft cap surfaced as 413.
- Exact `ContextSnapshot` payload schema (goal, constraints, artifacts, decisions,
  references). Assumed: opaque JSONB with a required inner `schema_version`, so
  `mctl-agents` can evolve it without an mctl-api release.
