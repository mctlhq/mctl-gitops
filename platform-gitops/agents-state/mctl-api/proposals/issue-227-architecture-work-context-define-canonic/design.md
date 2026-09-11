# Design: issue-227-architecture-work-context-define-canonic

## Current state

mctl-api is a Go 1.25 chi/v5 REST API plus an MCP server in one binary
(`cmd/api/main.go`, `internal/api/router.go`, `internal/mcp/server.go`). There is
no resource today that represents "a piece of work a human asked for". Grep for
`WorkItem`, `working context`, `ContextSnapshot`, `conversation`, `session`,
`idempotency`, `correlation` across Go code, `internal/openapi/openapi.yaml`,
`README.md`, `LLMS.md` and `CHANGELOG.md` returns no domain match. The OpenAPI
resource vocabulary (`internal/openapi/openapi.yaml`, `components.schemas` at
line 51) is `Tenant`, `Service`, `ArgoStatus`, `WorkflowStatus`, `AuditEntry`,
`ResourceUsage`, `LogLine`, `Operation`, `ExecuteRequest/Response`,
`PlatformSkill*`, `AgentDefinition`, `AgentVersion`, `AgentRelease`,
`AgentExecution`, `Error`; the last declared path is
`/api/v1/agents/dev-loop/{workflow_id}/approve` (line 1877).

What exists instead is execution- and event-shaped state owned by the engines
that produced it:

- `agent_executions` (`internal/agentregistry/store.go:113-132`) — one row per
  DevLoopWorkflow agent step, keyed
  `UNIQUE (temporal_workflow_id, agent, argo_workflow_name)`. It exists precisely
  because Argo objects expire under `ttlStrategy.secondsAfterCompletion`. But it
  has no owner/actor column, no lifecycle, is admin-only
  (`internal/api/handlers_agent_registry.go`), and `validPhase`
  (`store.go:162`) accepts only terminal phases `Succeeded|Failed|Error` — it is a
  post-hoc step log, not resumable work state.
- `audit.Entry` (`internal/audit/logger.go:26-43`) — append-only action log keyed
  on `WorkflowName`, with `Status` closed out later by the Argo webhook or
  `internal/api/audit_reconcile.go`. It answers "who did what", not "what is in
  flight for whom".
- `alerts.Alert` (`internal/alerts/types.go:52`) — the only tenant-scoped record
  with a real lifecycle (`open`/`analyzing`/`fix_proposed`/`acknowledged`/
  `resolved`/`suppressed`, plus the virtual `active` filter at `types.go:39`), but
  it is incident-shaped: `Severity`, `Fingerprint`, `Source: alertmanager|polling|
  github_webhook`. Reusing it would conflate "something broke" with "a human asked
  for work".
- The live Temporal workflow. `internal/api/handlers_dev_loop.go:229-280`
  (`GetDevLoopWorkflow`) documents its own ceiling: it returns only Temporal's
  short execution status plus a best-effort `shepherd_in_loop` query, and the MCP
  tool description states it "does not distinguish which step a Running execution
  is on" and 404s once retention lapses. It cannot be the source of truth for
  durable work state.

Identity has no notion of a surface. `auth.User` is `{ID, Groups, service}`
(`internal/auth/oidc.go:39-51`); the unexported `service` bit is the repo's
precedent for provenance that "is proof of how the caller authenticated, not a
claim anyone can make". `auth.Middleware` (`oidc.go:215`) resolves four token
paths (dev user, local OAuth JWT, Dex JWKS, GitHub PAT, plus the static
`MCTL_AGENT_SERVICE_TOKEN` service principal at `oidc.go:189-198`) but records
nothing about which path ran. Authorization is `user.IsAdmin()` /
`user.HasTenantAccess(tenant)` evaluated per request inside handlers
(`internal/api/handlers_alerts.go:53`, `handlers_domains.go:200`). Telegram
identity is only an operation parameter: `parseTelegramOwnerIDs`
(`internal/api/handlers_openclaw.go:40`) turns `telegram_owner_ids` into workflow
params for the OpenClaw bot allowlist; mctl-api never maps a Telegram ID to a
principal. ChatGPT appears only as an OAuth redirect-URI allowance
(`cmd/api/main.go:592`). The MCP transport is deliberately stateless — no
`Mcp-Session-Id` (`internal/api/router.go:366`, `internal/mcp/server.go:62`) — so
there is no server-side session to hang context off.

Persistence conventions are uniform and simple. Each store is a `pgxpool.Pool`
plus one `pool.Exec` of a `CREATE TABLE IF NOT EXISTS` schema constant; there is
no migration tool, and schema evolution is additive `ALTER TABLE ... ADD COLUMN
IF NOT EXISTS` / `DROP INDEX IF EXISTS` lines inside that same constant
(`internal/alerts/store.go:59-66`, `internal/audit/postgres.go:44-46`). Stores are
optional pointer fields on `api.Options` and a nil store means 503 plus a startup
warning naming the routes (`internal/api/router.go:40-127`, `:152-155`). Wiring
goes through `postgresURL` (`cmd/api/main.go:639`, enforcing TLS via
`internal/dburl`) and the generic `initStore` retry ladder (`main.go:699`,
6 attempts / 250 ms base) inside one shared `storeInitBudget = 8 * time.Second`
(`main.go:675`). Env vars follow `X_DB_URL` with an `AUDIT_DB_URL` fallback
(`ALERT_DB_URL`, `AGENT_REGISTRY_DB_URL`, `DOMAINS_DB_URL`, `OAUTH_DB_URL`).

There are strong concurrency precedents to reuse and no HTTP-level ones at all —
no `ETag`, `If-Match` or `Idempotency-Key` exists anywhere in the repo. At the
store layer: partial unique index plus `ON CONFLICT` dedupe
(`alerts_tenant_fingerprint_open`, `internal/alerts/store.go:59-66,118`),
idempotent-create-returns-existing (`internal/domains/store.go:88-92`),
at-least-once activity dedupe (`agent_executions`' UNIQUE key, rationale at
`internal/agentregistry/store.go:104-112`), advisory-lock-serialized
read-modify-write inside one transaction (`agentregistry.promote`,
`store.go:337-425`, including the deliberate idempotent no-op branch at `:381`),
and a replay grace window with serialization-failure retries
(`internal/auth/refreshstore/postgres.go:59-63,86,118-141`). The only correlation
ID today is the chi request ID surfaced through `internal/api/clientmeta.go` and
persisted as `audit_events.request_id` (`internal/audit/postgres.go:41`).

## Proposed solution

Introduce `WorkItem` as a new first-class resource owned by mctl-api, in a new
`internal/workitems` package modelled directly on `internal/domains` and
`internal/agentregistry`. Executions stay owned by their engines; the work item
holds only *correlation references* to them. `ContextSnapshot` rows are
append-only children of an execution. Surfaces become adapters: they read and
write this contract and keep only rendering/transcript state locally.

### Why a new resource and not an existing one

The issue asks explicitly whether an existing task/execution resource can own
this. It cannot: `agent_executions` is an admin-only terminal-phase step log with
no actor or lifecycle; `audit.Entry` is append-only and workflow-keyed;
`alerts.Alert` is incident-shaped; the Temporal execution is opaque and
TTL-bounded. Bending any of them would produce exactly the "parallel conversation
database" the roadmap forbids — just hidden inside a resource whose semantics say
something else. A new, narrow resource that stores *references, not transcripts*
is the smaller change.

### Data model (`internal/workitems`, PostgreSQL)

One schema constant, `CREATE TABLE IF NOT EXISTS` only, following existing style:

- `work_items` — `id TEXT PRIMARY KEY` (`wi_<uuid>`, via the already-vendored
  `github.com/google/uuid`), `tenant`, `owner_principal`, `visibility`
  (`tenant`|`private`), `origin_surface`, `title`, `external_key`, `state`,
  `waiting_reason`, `superseded_by`, `state_version INTEGER NOT NULL DEFAULT 1`,
  `created_by`, `created_at`, `updated_at`, `completed_at`, `idempotency_key`.
  Indexes: `(tenant, state)`, `(owner_principal)`,
  `UNIQUE (tenant, idempotency_key) WHERE idempotency_key <> ''`, and
  `UNIQUE (tenant, external_key) WHERE external_key <> '' AND state NOT IN
  ('completed','superseded','archived')` — the same partial-unique-index dedupe
  shape as `alerts_tenant_fingerprint_open`, so opening the same GitHub issue from
  Telegram and from the CLI converges on one work item.
- `work_item_events` — append-only lifecycle log: `id`, `work_item_id`, `seq`,
  `kind` (`created`|`state_changed`|`resumed`|`intent_appended`|
  `execution_attached`|`approval_requested`|`approval_decided`|`surface_linked`),
  `from_state`, `to_state`, `actor_principal`, `surface`, `request_id`,
  `detail JSONB`, `created_at`, `UNIQUE (work_item_id, seq)`. `request_id` is the
  existing chi request ID from `clientmeta`, which makes the audit log and the
  work-item history joinable without a new mechanism.
- `work_item_intents` — `id`, `work_item_id`, `seq`, `actor_principal`, `surface`,
  `text` (bounded, secret-scanned), `params JSONB`, `idempotency_key`,
  `created_at`, `UNIQUE (work_item_id, seq)`,
  `UNIQUE (work_item_id, idempotency_key) WHERE idempotency_key <> ''`.
- `work_item_executions` — `id` (`we_<uuid>`), `work_item_id`, `engine`
  (`temporal`|`argo`), `engine_ref`, `attempt INTEGER`,
  `resumed_from_execution_id`, `phase` (`Pending`|`Running`|`Succeeded`|`Failed`|
  `Error`), `started_at`, `ended_at`, `idempotency_key`,
  `UNIQUE (work_item_id, engine, engine_ref)`, plus
  `UNIQUE (work_item_id) WHERE phase NOT IN ('Succeeded','Failed','Error')` to
  enforce "at most one live execution per work item". `engine_ref` is the join key
  to `agent_executions.temporal_workflow_id` / `.argo_workflow_name` and to
  `audit.Entry.WorkflowName`; deliberately no FK, because `agent_executions` is
  itself intentionally unconstrained (`internal/agentregistry/store.go:98-102`)
  and may live in a different database.
- `work_item_snapshots` — `id` (`cs_<uuid>`), `work_item_id`, `execution_id`,
  `seq`, `snapshot_json JSONB` (opaque to mctl-api, carries its own inner
  `schema_version` so `mctl-agents` can evolve the payload without an mctl-api
  release), `content_hash`, `produced_by`, `created_at`,
  `UNIQUE (work_item_id, execution_id, seq)`. The store exposes only `Append` and
  read methods — no update/delete path exists, which is what makes "multiple
  executions without mutating history" structural rather than aspirational.
- `work_item_approvals` — `id`, `work_item_id`, `execution_id`, `kind`, `state`
  (`pending`|`granted`|`denied`|`expired`), `signal_engine`, `signal_ref`,
  `signal_name`, `requested_by`, `requested_at`, `decided_by`, `decided_at`,
  `reason`, `expires_at`, `UNIQUE (work_item_id) WHERE state = 'pending'`.
- `work_item_surface_refs` — `id`, `work_item_id`, `surface`, `external_id`
  (chat/thread/run identifier needed for reply routing), `actor_external_id`,
  `first_seen_at`, `last_seen_at`,
  `UNIQUE (work_item_id, surface, external_id)`.
- `surface_identity_links` — `surface`, `external_id`, `principal`, `linked_at`,
  `linked_by`, `PRIMARY KEY (surface, external_id)`. The only way a
  surface-native ID resolves to a principal, and it can only be created by an
  authenticated call from that principal. `telegram_owner_ids`
  (`internal/api/handlers_openclaw.go:40`) stays what it is today — a deployment
  allowlist, never an identity proof.

### Lifecycle

States: `active`, `waiting` (with `waiting_reason` = `input` | `approval`), and
terminal `completed`, `superseded`, `archived`. `resumed` is an *event*
(`work_item_events.kind`), not a state: a persisted `resumed` state would be
indistinguishable from `active` for every consumer while doubling the transition
table. A virtual list filter `open` means "any non-terminal", mirroring
`alerts.StatusActive`. The transition table lives in one exported map in
`internal/workitems/types.go` and is the single enforcement point; anything not in
it is a 409.

### Durable vs surface-local

Durable (mctl-api): lifecycle, owner/tenant/visibility, bounded normalized
intents, execution and snapshot correlations, approvals, surface references,
event history. Surface-local (adapter): raw transcripts, message formatting,
typing/scroll/UI state, per-message IDs beyond the correlation tuple, retry
buffers. Enforcement: intent text is capped at 8 KiB and passed through
`secretscan.Scan` before insert — the same gate `handlers_openclaw.go:655`,
`handlers_openclaw_identity.go:155` and `handlers_platform_skills.go:261` already
apply — so the contract cannot quietly become a transcript sink.

### Identity, authorization, approvals

The acting principal always comes from `auth.UserFromContext`; a `surface` field
on a request is untrusted metadata used for attribution and is accepted only when
it matches a `surface_identity_links` row for that principal (or the caller is
the service principal reporting on a link that already exists). Nothing is added
to `auth.User`: its `service` bit sets the precedent that provenance must be
unforgeable, and a surface claim arriving in a JSON body is not. Authorization is
re-evaluated on every request via `user.IsAdmin()` / `user.HasTenantAccess()` plus
the `visibility` check; because each surface transition is a fresh authenticated
HTTP request through `opts.AuthMiddleware`, re-evaluation is structural rather
than a rule someone must remember.

Approvals keep the runtime gate where it already is. `work_item_approvals` is the
durable request and record; `POST .../approvals/{id}/decision` takes the decider
from the verified caller only, rejects a body that carries a different decider
(the exact rule `ApproveDevLoopWorkflow` enforces at
`internal/api/handlers_dev_loop.go:166-177` after gitops#986), projects the grant
to the engine via the existing `DevLoopClient.SignalApprove`, and marks the row
`granted` only after that signal succeeds. Denials and expiries never signal.

### Concurrency and idempotency

Three layers, all with existing precedent:

1. `Idempotency-Key` header (or `idempotency_key` body field) on every mutating
   route, enforced by the partial unique indexes above; a replay returns the
   stored entity with 200 instead of 201. This is a new HTTP-level convention —
   the repo has none — so it is documented once in
   `docs/work-context-contract.md` and applied uniformly.
2. Optimistic concurrency on `state_version` for state-changing routes:
   `expected_state_version` in the body, mismatch -> 409 carrying the current
   state and version. A body field rather than `If-Match` because no ETag
   plumbing exists anywhere in the repo and MCP tool arguments are flat strings,
   which would make a header-only contract unusable from the MCP surface later.
3. Store-level serialization: every mutation runs in one transaction opened with
   `pg_advisory_xact_lock(hashtext('workitem:' || id))`, copied from
   `agentregistry.promote` (`internal/agentregistry/store.go:337-349`), including
   its idempotent-no-op branch pattern so a lost response cannot corrupt history.

### REST surface (`workitem/v1`)

Mounted in `internal/api/router.go` inside the authenticated group; the mutating
routes join the existing 20/min write group alongside `/operations/{name}/execute`
and the dev-loop routes, and reads stay outside it (same reasoning already written
down for `GET /agents/dev-loop/{workflow_id}`):

- `POST /api/v1/work-items` — open (idempotent)
- `GET /api/v1/work-items` — list, tenant/state/owner filtered, default `open`
- `GET /api/v1/work-items/{id}` — current state: work item, latest execution,
  pending approval, latest snapshot pointers, `state_version`
- `PATCH /api/v1/work-items/{id}` — state transition (`complete`, `archive`,
  `supersede`, `wait`), requires `expected_state_version`
- `POST /api/v1/work-items/{id}/intents` — append user intent
- `GET|POST /api/v1/work-items/{id}/executions` — list / attach-correlate
- `GET|POST /api/v1/work-items/{id}/executions/{execution_id}/snapshots`
- `POST /api/v1/work-items/{id}/resume` — new execution continuing a prior one
- `GET /api/v1/work-items/{id}/approvals`,
  `POST /api/v1/work-items/{id}/approvals/{approval_id}/decision`
- `POST /api/v1/work-items/{id}/surface-refs` — correlate a surface reference
- `GET /api/v1/work-items/{id}/events` — lifecycle history
- `POST /api/v1/work-items/surface-identities` — link the caller's principal to a
  surface-native ID

Every payload carries `"schema_version": "workitem/v1"`. The contract is published
in `internal/openapi/openapi.yaml` (new `WorkItem`, `WorkItemEvent`,
`WorkItemIntent`, `WorkItemExecution`, `ContextSnapshot`, `WorkItemApproval`,
`SurfaceRef` schemas) and narrated in a new `docs/work-context-contract.md`, which
is the artifact the "canonical ownership model is documented" criterion names.
Wiring adds `WorkItemStore *workitems.Store` to `api.Options` with the
nil-store-means-503 warning, and `WORK_ITEMS_DB_URL` with an `AUDIT_DB_URL`
fallback in `cmd/api/main.go`, initialized through `postgresURL` + `initStore`
inside the existing shared `initCtx`. A `WORK_ITEMS_DISABLED` kill switch checked
before construction gives a config-only off ramp that does not require also
removing the shared `AUDIT_DB_URL` fallback that alerts, domains and the agent
registry depend on.

Retention is a lightweight sweeper goroutine in `cmd/api/main.go` (one ticker,
two `DELETE` statements) governed by `WORKITEM_SURFACE_RETENTION_DAYS` (default
90, purging intent text and surface refs while keeping the item and its
correlations) and `WORKITEM_RETENTION_DAYS` (default 365, purging terminal
items). Audit entries for work-item operations carry `work_item_id` and never
intent text or surface external IDs in `audit.Entry.Parameters`.

## Alternatives

1. **Extend `agent_executions` / make the Temporal `DevLoopWorkflow` the source of
   truth.** Rejected: `agent_executions` records only terminal phases
   (`validPhase`, `internal/agentregistry/store.go:162`), has no actor, owner,
   lifecycle or approval concept, and is admin-only; and the Temporal execution is
   explicitly opaque about which step it is on and disappears after retention
   (`internal/api/handlers_dev_loop.go:229-262`). A durable work item must outlive
   and precede any execution — including the case where zero executions have run
   yet — which is structurally incompatible with an execution-keyed table.
2. **Overload `alerts.Alert` as a generic "work" record.** It is the closest
   existing shape (tenant-scoped, lifecycle, virtual `active` filter, dedupe by
   fingerprint). Rejected: its columns and sources are incident semantics
   (`Severity`, `Fingerprint`, `SourceAlertManager`), the incident MCP/REST surface
   and the incident-responder cron already read it with those semantics, and every
   consumer would need to learn "an alert that is not an alert". Renaming later
   would be a breaking change to a live contract.
3. **Keep state per surface and correlate lazily (for example a thin
   `surface_links` join table only).** Rejected: it is exactly the parent
   roadmap's anti-goal. Every surface would need its own lifecycle, approval and
   resume logic; `mctl-telegram` would become a second control plane; and
   cross-surface resume would depend on whichever surface happened to hold the
   newest copy.
4. **Store the contract in gitops (`platform-gitops/agents-state/...`) like
   proposals and `.status.yaml`.** Rejected: work state is high-frequency,
   per-user and privacy-bearing; commit-per-transition cannot give optimistic
   concurrency or sub-second reads, and the repo has already been moving the other
   way (`internal/domains`' package doc records replacing an external write path
   with mctl-api's own store).

## Platform impact

**Migrations.** Additive only: seven new tables created by one
`CREATE TABLE IF NOT EXISTS` schema constant, in the same style as
`internal/alerts` and `internal/domains`. No existing table is altered, no data is
backfilled, and no migration tool is introduced (the repo has none). The store is
optional: with `WORK_ITEMS_DB_URL` and `AUDIT_DB_URL` both unset, nothing is
created and every `/api/v1/work-items*` route returns 503.

**Backward compatibility.** Purely additive to the REST and OpenAPI surface. No
existing route, response shape, MCP tool, Argo workflow or gitops path changes.
Existing `agent_executions`, `audit_events` and `alerts` rows keep their current
meaning; correlation is forward-only, so no historical data is reinterpreted. MCP
tools are deliberately not added in this proposal, so
`internal/mcp/server_test.go`'s `TestNewMCPServer_ToolCount`,
`internal/mcp/annotations_test.go`'s `recordedHints` and
`docs/portal-allowlist.json` (guarded by `internal/mcp/portal_allowlist_test.go`)
are untouched.

**Resource impact.** One more `pgxpool` against the same PostgreSQL instance most
deployments already use for audit. Row volume is small (one work item per user
request, a handful of children each); snapshots are the only large payload, capped
at 256 KiB with a per-item soft cap returning 413. The new store must be
initialized inside the shared `storeInitBudget = 8 * time.Second`
(`cmd/api/main.go:675`) alongside the four existing stores — the one real startup
risk, since exceeding it pushes the listener past the readiness probe's
`initialDelaySeconds`. Mitigation: reuse `initStore`'s ladder unchanged, keep the
schema constant to plain `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX` with no
`CONCURRENTLY`, and verify startup timing in the smoke test.

**Risks and mitigations.**

- *Scope creep into a chat database.* Mitigated by the 8 KiB intent cap, the
  `secretscan.Scan` gate, the absence of any transcript field, and a test that
  asserts no store method updates or deletes a snapshot.
- *Two sources of truth for approvals.* Mitigated by keeping the engine's gate
  authoritative: the work-item row is granted only after `SignalApprove` returns,
  and denial never signals.
- *Surface-ID spoofing / identity confusion.* Mitigated by
  `surface_identity_links` being the only resolution path, principals always coming
  from the verified token, and `telegram_owner_ids` explicitly remaining a
  deployment allowlist.
- *Lost or duplicated writes when two surfaces act at once.* Mitigated by the
  three-layer idempotency/concurrency design, with the advisory-lock transaction
  copied from a code path already hardened for this exact class of bug.
- *Privacy exposure through audit logs.* Mitigated by logging only
  `work_item_id` in `audit.Entry.Parameters` and by the retention sweeper.
- *Contract churn for adapter authors.* Mitigated by the `workitem/v1`
  `schema_version` label on every payload, an opaque `snapshot_json` with its own
  inner version, and a documented rule that breaking changes ship as a new label.
