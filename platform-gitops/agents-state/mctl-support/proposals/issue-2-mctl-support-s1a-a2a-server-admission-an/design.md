# Design: issue-2-mctl-support-s1a-a2a-server-admission-an

## Current state

The repository holds only the stack bootstrap (mctl-support#1, commit `cd11c40`):

- `pyproject.toml` pins `a2a-sdk[http-server,sql,postgresql]==1.2.3`,
  `anthropic==2.3.0` and `uvicorn==0.41.0` for Python `>=3.12,<3.13`. Dev
  tools are `pytest` and `ruff` (line length 100). The package is
  `src/mctl_support`, built with hatchling.
- `src/mctl_support/__init__.py` contains only `__version__ = "0.0.0"`.
- `tests/test_stack.py` checks the pinned versions and that the SDK modules
  the spike used import: `a2a.server.routes`, `a2a.server.request_handlers`,
  `a2a.server.cluster`, `a2a.server.agent_execution` and `a2a.server.tasks`.
- `uv.lock` resolves `sqlalchemy[asyncio,postgresql-asyncpg]` 2.1.x,
  `asyncpg` 0.32 and `starlette` through the SDK extras.
- `.github/workflows/ci.yml` runs `uv sync --locked`, `ruff check`,
  `ruff format --check` and `pytest -q`. It has no Postgres service yet.
- `AGENTS.md` sets the rules this design follows. Tenant isolation is
  enforced by mctl-api, and the service holds no admin token and no
  ServiceAccount token. A failed read is an error. A foreign `contextId` gets
  the same answer whether it exists or not. Task state lives in Postgres. A
  duplicate `messageId` is reserved before the task exists. Cancel works
  across replicas and the token is revoked.
- There is no Dockerfile, no service code, no migrations and no deploy
  manifest. The spike prototype (`docs/spikes/mctl-support-runtime/python/`)
  and its `gate/gate.py` are in mctlhq/.github and are not in this clone.
  The exact SDK class names below are therefore taken from the module list
  in `tests/test_stack.py` and must be matched against the prototype during
  implementation.

Deployed state checked:
- `mctl_get_tenant admins`: no `mctl-support` service is deployed. Quotas are
  pods 12, services 10, requests.memory 2Gi. Networking:
  `allowIntraNamespace`, `allowClusterEgress` and `allowInternetEgress` are
  all true. One member: `mashkovd`.
- `mctl_get_resource_usage admins`: used pods 8/12, services 8/10,
  requests.cpu 350m/2, requests.memory 1152Mi/2Gi, PVCs 0/2. Two replicas,
  a rolling-update surge pod and no extra CronJob pod fit; a separate
  CronJob pod would make the margin tight.
- `mctl_list_services namax66`: one service, `news-factory` (base-service,
  synced). This is the target of the live probe.
- `mctl_get_agent mctl-support`: refused as "outside the investigate scope
  of this agent run". I could not observe whether the agent definition is
  already registered, so this is unknown, not absent.
- `$MCTL_GITOPS_ROOT/tenants/admins/values.yaml`: `podSecurityLevel:
  restricted`, `networking.allowInternetEgress: true`, no `teams`.
- `$MCTL_GITOPS_ROOT/helm-charts/tenant/templates/networkpolicy.yaml`:
  - Namespaces are `<tenant>`, or `<tenant>-<team>` for each `teams[]` entry.
  - There is a default deny.
  - `allow-cluster-egress` covers DNS and the in-cluster CIDRs.
  - `allow-internet-egress` is `0.0.0.0/0` minus RFC1918 and the node public
    CIDRs.
  - No `CiliumNetworkPolicy` or `toFQDNs` exists anywhere in mctl-gitops
    (grep), so there is no platform FQDN egress mechanism.
- `$MCTL_GITOPS_ROOT/helm-charts/base-service/values.yaml`: supports
  `replicaCount`, `automountServiceAccountToken`,
  `serviceAccount.create: false`, hardened `podSecurityContext` and
  `containerSecurityContext` defaults (seccomp `RuntimeDefault`, dropped
  capabilities, non-root, read-only root), `ingress`, a database
  `externalSecret` (Vault `teams/<team>/<app>/database`, giving
  `DATABASE_URL`, `DB_HOST` and so on), `job-db-init` and `extra-objects`.
- `$MCTL_GITOPS_ROOT/services/labs/kuptsi-app/values.yaml` shows the platform
  DB host `shared-pg-rw.platform-db.svc.cluster.local:5432` with an asyncpg
  `DATABASE_URL`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-web/values.yaml` is the pattern for
  an admins base-service with ingress and cert-manager `letsencrypt-prod`.
- `$MCTL_GITOPS_ROOT/agent-platform/README.md`: per ADR 007, canonical
  AgentDefinitions live in the source repo, published versions and bindings
  live in the mctl-api registry, and execution profiles live in
  `agent-platform/execution-profiles/`. No `mctl-support` profile exists.

## mctl-api contract (amendment, verified 2026-10-27 on mctl-api main)

Reviewer amendment. The investigator could not read mctl-api, so these are
the endpoints as they exist, checked in code. `HttpMctlApi` uses exactly
these; every non-2xx is an error, never an empty result.

| Step | Call (caller's bearer unless noted) | Notes |
|---|---|---|
| whoami | `GET /api/v1/whoami` -> `{id, groups, isAdmin, namespaces}` | There is no principal id field. The owner key for tasks, contexts and reservations is `id`. `groups` are the tenant memberships; `namespaces` is informational and must not be used for admission. |
| work item | `POST /api/v1/work-items` `{tenant, title, external_key: "mctl-support:<task_id>", idempotency_key: <task_id>}` | One work item per support task. Needs the `developer` role on the tenant: a viewer gets 403, and the task fails with an explicit reason (S1a limitation, recorded in the README). |
| execution | `POST /api/v1/work-items/{id}/executions` `{engine: "a2a", engine_ref: <task_id>, phase: "Running", idempotency_key: ...}` | The `a2a` engine is added by mctl-api#824 and must be released before this service is deployed. At most one non-terminal execution per work item. |
| mint | `POST /api/v1/agent-run-tokens` `{agent: "mctl-support", execution_id: <we_id>, scope: "support", tenant}` | `permissions` must be absent (400 otherwise). The response carries the plaintext token once. The agent must be registered first (task 11). |
| finish | `POST /api/v1/work-items/{id}/executions` with the same `engine`/`engine_ref` and a terminal phase | Same call as attach; mctl-api updates the phase. Phases are `Pending`, `Running`, `Succeeded`, `Failed`, `Error`. Map A2A `completed` to `Succeeded`, `failed`/`rejected`/`canceled` to `Failed`. A terminal phase makes the run token read as revoked. |
| revoke | `POST /api/v1/agent-run-tokens/self/revoke` with the run token | Called as well in the `finally`, so the token dies even when the finish call fails. Its TTL is the last backstop. |

Consequences for the design below:
- The bearer is held in the memory of the task's executor coroutine until
  the task finishes, not only for the request, because the finish call
  needs it. It is never persisted or logged. If the replica dies, the
  self-revoke cannot run and the token's TTL applies.
- `MCTL_API_URL` is configuration. The deployment decides between the public
  `https://api.mctl.ai` and the in-cluster Service; the code does not assume
  either.

## Build and release (amendment)

Source repositories do PR validation only (lint, tests,
`docker build` without push). The image is built and pushed by mctl-gitops
(`build-image.yaml` / `release-deploy.yaml`, dispatched with the repo, ref
and tag), which also bumps `image.tag`. This repo must not add a GHCR push,
a tag-triggered build or a gitops token.

## Proposed solution

### Package layout (`src/mctl_support/`)

| Module | Responsibility |
|---|---|
| `config.py` | Pydantic-free dataclass loaded from the environment: `DATABASE_URL`, `MCTL_API_URL`, `SUPPORT_ALLOWED_TENANTS` (comma list, default `namax66`), `SUPPORT_EXECUTOR` (`fake` / `agent`), `SUPPORT_ENV`, `SUPPORT_PUBLIC_URL` (`https://support.mctl.ai`), `MCTL_AUTH_ISSUER`, retention durations, and the provider capability `server_thread` (unused until S1b, but defined here per AGENTS.md). |
| `app.py` | `create_app(config, *, clock, mctl_api, executor)` builds the Starlette app from the SDK's REST routes (`a2a.server.routes`), the default request handler (`a2a.server.request_handlers`), the SQL task store (`a2a.server.tasks`) and the cluster-aware queue/cancel support (`a2a.server.cluster`). It also adds `/healthz` and `/readyz`, and starts the retention loop in the lifespan. `__main__.py` runs it with uvicorn. |
| `agent_card.py` | Builds the A2A 1.0 `AgentCard`: one `diagnose` skill, the HTTP+JSON interface at `SUPPORT_PUBLIC_URL`, `capabilities.streaming=false` and `pushNotifications=false`, and `securitySchemes.mctl` of type OAuth 2 (authorization-code flow) with URLs from mctl-api's authorization-server metadata (`MCTL_AUTH_ISSUER`), plus `security: [{mctl: []}]`. |
| `admission.py` | Starlette middleware and `Admission` service. It checks the bearer, resolves the principal and tenant, and applies the allowlist. The result is an immutable `Caller(principal_id, tenant, is_admin, bearer)` placed in the SDK `ServerCallContext` state. The bearer is kept only in request memory. |
| `mctl_api.py` | The `MctlApi` protocol and an `HttpMctlApi` implementation over `httpx`, which the SDK already depends on. Methods: `whoami(bearer)`, `create_execution(bearer, tenant, task_id) -> we_id`, `mint_support_token(bearer, we_id)`, `finish_execution(bearer_or_token, we_id, phase)`. Any non-2xx or transport error raises `MctlApiUnavailable` or `MctlApiDenied`; there is never an empty default. `FakeMctlApi` is used for tests. |
| `ownership.py` | A wrapper around the SDK task store (`OwnedTaskStore`) that filters every `get` by `owner_principal_id` and returns `None` (giving SDK `TaskNotFoundError`) for a foreign or missing task. It also includes the context-ownership check used before an executor sees a `contextId`. |
| `idempotency.py` | `reserve_message(session, principal, message_id, digest) -> ReservationResult(new or existing task_id)`. Task id = `uuid5(MCTL_SUPPORT_NS, f"{principal}:{message_id}")`, inserted into `message_reservations` with `ON CONFLICT DO NOTHING RETURNING`. On conflict it loads the stored digest. Same digest means the existing task is returned; a different digest means invalid params. |
| `store/schema.py` + `migrations/` | SQLAlchemy Core tables, created by a versioned migration step run from the chart's `job-db-init` (or a `python -m mctl_support.migrate` init container). The SDK's own task table is created through its SQL store helper in the same step. |
| `retention.py` | `run_retention(session, now)` deletes by the D10 windows. The `RetentionLoop` runs every hour in each replica, takes `pg_try_advisory_lock(<const>)`, runs one pass and releases the lock. |
| `executors/fake.py` | `FakeExecutor(AgentExecutor)`: scripted behaviour keyed by message text (`answer`, `slow`, `ask`, `fail`). `slow` emits `working` and then sleeps in small steps, checking for cancellation. |
| `executors/lifecycle.py` | Wraps any executor. Before it runs: create the WorkItemExecution and mint the run token. After a terminal state, or on cancel: call `finish_execution`. The token is held in memory only. |

### Tables (platform Postgres, database `admins-mctl-support`)
- `contexts(context_id pk, owner_principal_id, tenant, created_at, last_activity_at)`.
- `message_reservations(principal_id, message_id, task_id unique, content_digest, created_at, primary key (principal_id, message_id))`.
- `task_owners(task_id pk, owner_principal_id, tenant, context_id fk, work_item_execution_id, created_at, terminal_at)`. This sits next to the SDK's task table, which holds A2A status and history.
- `transcripts(task_id, seq, role, parts jsonb, created_at)`. Message bodies are stored here so they can be expired before task metadata, and the SDK task history copy is trimmed by the same retention pass.

The context is created by the server. A client-supplied `contextId` must match
a row with the same owner principal and tenant; any other case gets the
error used for "context not found". Two consequences follow. Existence is
never revealed, and a client cannot plant a context id.

### Request flow for `POST /message:send`
1. The admission middleware runs `whoami(bearer)`. It gives 401 on a missing
   or rejected bearer and 503 on an mctl-api error.
2. It selects the tenant: the single membership, or `metadata.tenant` when
   it is in the memberships. Anything else gives 403.
3. Allowlist: `tenant in SUPPORT_ALLOWED_TENANTS or is_admin`, else 403.
   Nothing has been written at this point.
4. In one transaction:
   - check context ownership;
   - reserve `(principal, messageId)`;
   - insert `task_owners`;
   - insert or touch the context.
   A conflict returns the existing task through the ownership-filtered store.
5. Only for a new task, the lifecycle wrapper:
   - creates the WorkItemExecution;
   - mints the token;
   - runs the executor through the SDK request handler, which emits
     `submitted`, `working`, and then a terminal or `input-required` state.
6. A follow-up message on an `input-required` task follows the same path. It
   resolves the task through the ownership-filtered store, and the reserved
   `messageId` of the follow-up gives it its own idempotency.

### Cancel across replicas
`POST /tasks/{id}:cancel` resolves ownership and then calls the SDK cancel.
The SDK's `a2a.server.cluster` support was used by the spike for
cross-replica queues and cancel; it is the first choice. If it turns out not
to deliver cancel to the owning replica, the fallback is a `cancel_requested`
flag plus `NOTIFY support_cancel, '<task_id>'`. Each replica `LISTEN`s and
cancels the matching local `asyncio.Task`; a 1 s poll of the flag covers a
dropped notification. The lifecycle wrapper's `finally` calls
`finish_execution(we, canceled)`, which revokes the run token. Its TTL is the
backstop if the replica dies.

### Agent registration
Add the canonical definition `agent/agent.yaml` (identity `mctl-support`,
skill `diagnose`, scope `support`). Register it once in the mctl-api registry
(`mctl_create_agent` plus a published definition version) as an operator
step recorded in the PR. Add an execution profile
`agent-platform/execution-profiles/mctl-support-default/profile.yaml` in
mctl-gitops only if the registry binding requires one. The WorkItemExecution
calls name this agent.

### Deployment (mctl-gitops, `platform-gitops/services/admins/mctl-support/`)
- `values.yaml` on chart `base-service`:
  - `replicaCount: 2`, with `autoscaling.enabled: false`;
  - a `RollingUpdate` strategy with `maxSurge: 1` and `maxUnavailable: 0`;
  - `automountServiceAccountToken: false` and `serviceAccount.create: false`;
  - the chart's hardened security-context defaults, with numeric
    `runAsUser`/`runAsGroup` 10001 matching the Dockerfile `USER`;
  - `writablePaths` covering only `/tmp`;
  - `ingress` for `support.mctl.ai` with `letsencrypt-prod`;
  - the database `externalSecret` (`teams/admins/mctl-support/database`) and
    `job-db-init` for migrations;
  - requests of 50m CPU and 128Mi memory, and limits of 300m and 256Mi.
- A per-pod deny-by-default NetworkPolicy in `extraObjects` would not reduce
  the namespace-wide `allow-internet-egress`, because NetworkPolicies are
  additive. The PR therefore states the limitation in `values.yaml`
  comments: the pod can reach any public address. Everything else is
  constrained:
  - no ServiceAccount token;
  - no Kubernetes API use (port 6443 is in cluster egress, but there are no
    credentials);
  - mctl-api is reached at its in-cluster Service;
  - Postgres is reached at `shared-pg-rw.platform-db`.

  The durable fix is a dedicated namespace with `allowInternetEgress: false`
  plus an egress gateway or FQDN policy. That is tracked as an open question,
  not hacked in with Anthropic CIDRs.
- A `Dockerfile` (in this repo) based on `python:3.12-slim`: `uv sync
  --locked --no-dev`, numeric non-root `USER 10001`, and
  `CMD ["python","-m","mctl_support"]`.

### Why this shape
- The SDK owns protocol shape and task state, so only one transport exists
  (AGENTS.md).
- Admission lives in middleware so that no handler can be reached
  unauthenticated, and tests can delete the middleware and watch them fail.
- Deriving the task id from `(principal, messageId)` and adding a unique
  reservation makes duplicates collapse even when they race on two replicas.
  This is the spike review lesson.
- The retention loop runs in-process with an advisory lock, which avoids a
  CronJob pod against the tight admins pod quota (8/12) and keeps one code
  path testable with a clock.

## Alternatives
1. **Hand-written FastAPI REST routes over our own task tables.** Dropped:
   it duplicates the SDK's protocol mapping and would drift from A2A 1.0.
   AGENTS.md mandates the official SDK and one canonical binding.
2. **A Kubernetes CronJob for retention.** Dropped for S1a: it adds a pod
   and its image pull against a namespace already at 8/12 pods, and needs a
   second entrypoint. The advisory-lock loop gives the same single-run
   guarantee. It can move to a CronJob later without changing
   `run_retention`.
3. **Idempotency through an in-memory or Redis cache.** Dropped: it does not
   survive replica changes and adds a dependency. Postgres uniqueness is
   both durable and transactional with task creation.
4. **A new `support` tenant (own namespace, internet egress off)** to meet
   the issue's "namespace `support`" literally. Deferred: it means a new
   tenant entry, its Vault and ArgoCD scaffolding, and an egress path to
   Anthropic that the platform does not yet have. It is recorded as an open
   question rather than chosen silently.

## Platform impact
- **Migrations:** these are new tables in a new database
  (`admins-mctl-support`). There are no existing data and no
  backward-compatibility concerns. Migrations are forward-only and
  idempotent (`CREATE TABLE IF NOT EXISTS` plus a version table).
- **Resources:** two pods, each requesting 50m CPU and 128Mi memory, take
  admins to 10/12 pods (11 during a rollout), 9/10 Services and about
  1408Mi/2Gi memory requests. One more DB on the shared CNPG cluster.
- **Security risks and mitigations:**
  - Bearer leakage: the bearer is never persisted or logged, and a log
    filter redacts `Authorization`.
  - Admission bypass: the middleware is on all A2A routes; tests remove it
    and must fail.
  - Cross-principal probing: missing and foreign ids give identical
    not-found responses, asserted byte for byte in tests.
  - Fail-open on mctl-api outage: mctl-api errors give 503, never "allowed".
  - The fake executor in production is gated by an explicit flag. The S1a
    pilot deploys with the fake executor on purpose, until S1b.
- **Egress limitation:** internet egress stays namespace-wide in `admins`
  (see Deployment). The limitation is written down in values.yaml and is
  open in requirements.md.
- **External dependencies:** minting and WorkItemExecution endpoints from
  mctl-api#811 (S0a). If they are not live, task creation fails with an
  explicit `failed` reason, and the live probe waits.
- **CI:** a `postgres:16` service container in `ci.yml` for the store, the
  idempotency and the two-replica tests. The tests skip with a clear reason
  only when `DATABASE_URL` is unset locally, never in CI (enforced by
  `CI=true`).
