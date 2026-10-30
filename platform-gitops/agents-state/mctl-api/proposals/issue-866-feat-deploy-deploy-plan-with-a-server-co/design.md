# Design: issue-866-feat-deploy-deploy-plan-with-a-server-co

## Current state

### Deploy analyze (item `analyze`, shipped)

- `internal/deployanalyze/schema.go` embeds `schema/deploy-intent.schema.json` (`SchemaSHA256 = cd2e6f1d...386c4`, source `mctlhq/mctl-gitops:platform-gitops/agent-platform/schemas/deploy-intent.schema.json`) and exposes `Validate(map[string]any) error` over a compiled `santhosh-tekuri/jsonschema/v6` schema. The schema is closed everywhere (`additionalProperties: false`), has `spec.environment` enum `preview | production`, `source.revision` pattern `^[0-9a-f]{40}$`, `runtime.port` 1024-65535, `runtime.healthPath`, `runtime.replicas` 1-3, optional `resources`, `exposure.mode` `internal | public`, `env` (plain values), and `secretRefs[] {env, property}` with no Vault path.
- `internal/deployanalyze/github.go` defines `ContentReader` with `Commit(ctx, repo, sha) error` and `File(...)`, implemented by `HTTPReader`; errors map to `ErrRevisionUnreadable`, `ErrGitHubUnavailable`, `ErrGitHubMalformed`.
- `internal/api/handlers_deploy_analyze.go`: `DeployAnalyze` validates input, checks `user.HasTenantAccess(tenant)` (membership only, no role), resolves the binding through `SourceRepoBindingReader.ServicesBySourceRepo` and falls back to `repoBoundToTeam` (`internal/api/build_repo_gate.go`), then calls `deployanalyze.Analyze`. Every outcome is audited through the `deployAudit` helper (`refuse`, `set`, `write`) with coded errors via `writeErrorCode`. Routes: `r.Get("/deploy/analyze", ...)`, `r.Get("/deploy/bindings", ...)` in `internal/api/router.go`.
- MCP: `toolDeployAnalyze` in `internal/mcp/server.go`; `mctl_deploy_analyze` is listed in `governedAgentTools` in `internal/mcp/agent_receipt_gate.go` (every non-read-verb tool must be there, a test fails otherwise).

### Gitops reads

- `internal/gitops/reader.go`: one local checkout behind `r.mu`; `r.head` is the checkout HEAD (`Revision()`); `checkFreshLocked()` refuses an unsynced or stale checkout; `statServiceFileLocked(team, component, file)` walks `platform-gitops/services/<team>/<component>/<file>` with `Lstat`, returns `""` only for a documented absence and errors on symlinks, non-regular entries or a missing `services` directory; `ReadFiles` shows the pattern of reading files and the revision under one `RLock`. `ComponentSourceRepo` reads the `github.com/source-repo` annotation from `catalog-info.yaml`.

### What `deploy-service` writes (mctl-gitops)

- `argo-workflows/cluster-templates/tpl-git-commit.yaml` does the write. Onboard: picks `service-templates/default/values.yaml.tpl` (or `worker`, or an explicit template), `sed`-substitutes `__TEAM_NAME__`, `__SERVICE_NAME__`, `__IMAGE_TAG__`, `__PORT__`, `__HOST__`; host defaults to `${TEAM}-${SERVICE}.${PLATFORM_DOMAIN}` for `base-service`; adds a mirror host when `PLATFORM_DOMAIN_ALT` is set (it is `""` in `argo-workflows/config/mctl-platform-config.yaml`), the `cert-manager.io/cluster-issuer: letsencrypt-prod` annotation and `ingress.tls = [{secretName: <service>-tls, hosts: .ingress.hosts}]`; sets `.probes.liveness.path` / `.probes.readiness.path` from `health_check_path`; sets `.env[KEY]` per env line; for secrets sets `.externalSecret.targetSecret = <service>-secrets`, appends `{secretKey: KEY, remoteKey: teams/<team>/<service>, property: KEY}` and an `envFrom` secretRef; pins `containerSecurityContext.runAsUser/runAsGroup` from the built image's USER.
- Deploy (update): sets `.image.tag`, syncs `extraContainers` on the same image repository, merges `env` (or clears it), merges `externalSecret.data`/`envFrom` (or clears them). It never changes port, probes or ingress.
- `tpl-validate-tenant.yaml` derives `image_tag` from `image_tag`, else `git_tag` without a leading `v`, else `latest`.
- `wft-preview-deploy.yaml` reads `services/${TEAM}/${COMPONENT}/values.yaml` and installs a Helm release `preview-{app}-{id}` in `{team}-preview` with `--set image.tag`, preview host `{app}-{id}.{PLATFORM_DOMAIN}`; nothing in gitops is written.

### Operations registry and confirmation

- `internal/operations/registry.go`: `Operation.RequiresConfirm` is declared and set `true` on `create-tenant`, `provision-database`, `retire-service`, `delete-tenant`; `deploy-service` is `false` with `MinRole: RoleDeveloper`. No Go code reads `RequiresConfirm` (`grep -rn RequiresConfirm internal` finds only the struct field and registry literals).
- `internal/mcp/server.go`: `requireConfirm(args, subject)` checks `args["confirm"] == "yes"`. It is called by `mctl_retire_service`, `mctl_delete_tenant`, rollback, preview delete, domain removal and agent-registry tools, but **not** by `mctl_create_tenant` (posts to `/api/v1/operations/create-tenant/execute`) or `mctl_provision_database` (posts to `/api/v1/operations/provision-database/execute`). Gated tools `delete(params, "confirm")` before posting.
- `internal/api/handlers_write.go` `ExecuteOperation`: refuses `HandlerOnly` ops with 405, decodes `map[string]string`, authorizes CI principals (`authorizeCIDeploy`), drops undeclared keys with `Registry.StripUndeclared`, enforces `requireTenantRole(... op.MinRole ...)`. There is no confirmation check.

### Stores and digests

- `internal/workitems/store.go`: `NewStore` runs `CREATE TABLE IF NOT EXISTS` schema strings on connect (`pgshared.Open`); tests skip without `TEST_DATABASE_URL`. IDs carry prefixes (`types.go`: `wi_`, `we_`); `internal/principals/ulid.go` has `newPrefixedID(prefix, now)`.
- `internal/workitems/action_approvals.go`: `intentEncodingVersion = "mctl-action-intent/v1"`; `IntentHash` writes the version line then `<field>:<len>:<value>\n` per field and returns `sha256:<hex>`.
- `work_item_execution_requests.work_item_id` is `NOT NULL` (issue's reason for a separate record).

### Deployed state checked

- `mcp__mctl__mctl_get_service_config(team=mctl, service=mctl-api)`: error "service not found: mctl/mctl-api". mctl-api is not a catalogue service under that tenant; its deployed config was not observed through this tool.
- `$MCTL_GITOPS_ROOT/services/`: contains tenants `admins`, `karabu`, `labs`, `namax66`; no `mctl-api` service directory, so mctl-api's env (e.g. `PLATFORM_DOMAIN`, the work-items DB URL) was not observed in gitops. `cmd/api/main.go` defaults `PLATFORM_DOMAIN` to `mctl.ai`.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/tpl-git-commit.yaml`, `wft-deploy-service.yaml`, `wft-preview-deploy.yaml`, `tpl-validate-tenant.yaml`, `argo-workflows/service-templates/default/values.yaml.tpl`: read; summarized above.
- `$MCTL_GITOPS_ROOT/argo-workflows/config/mctl-platform-config.yaml`: `PLATFORM_DOMAIN_ALT: ""` (no mirror host today).
- Callers of the generic execute route outside this repository (mctl-portal, mctl-web, Backstage) could not be observed from this run; recorded under Open questions in requirements.md.

## Proposed solution

### 1. New package `internal/deployplan`

Pure, I/O-free core plus a Postgres store. Files:

- `intent.go`: `type Intent struct` mirroring the schema (typed fields), `ParseIntent(raw json.RawMessage) (*Intent, map[string]any, error)`. Order: decode into `map[string]any` with `UseNumber`, call `deployanalyze.Validate` (schema errors -> `ErrIntentInvalid` wrapping the `jsonschema.ValidationError` text), then decode again into `Intent` with `DisallowUnknownFields` as a belt-and-braces check. `Canonical(in *Intent) []byte` applies schema defaults (`dockerfile: Dockerfile`, `context: .`, `replicas: 1`) and emits JSON with sorted keys and no insignificant whitespace (marshal via `map[string]any` -> `encoding/json`, which sorts map keys). The canonical form is what is stored in `intent` and hashed.
- `compile.go`: `Compile(in *Intent, cur Current, cfg Config) (*Compiled, error)` where `Current{Exists bool; Values []byte}` and `Config{PlatformDomain, PlatformDomainAlt string; Template []byte}`. Returns `Compiled{Action, ValuesAfter []byte, Diff string, Host string}`.
  - **Compilable subset** (anything else is `ErrNotCompilable{Pointer}` -> 422 `deploy_intent_not_compilable`): `exposure.mode` must be `public`; `resources` absent or equal to the template's `resources`; `runtime.replicas` 1; every `secretRefs[i].env == secretRefs[i].property` (the workflow writes `secretKey` and `property` from the same key); on update, `runtime.port` must equal current `service.port` and `runtime.healthPath` must equal current probe paths (or the chart default when absent), because `deploy` never rewrites them.
  - **Onboard**: substitute the template exactly like the `sed` program (`__TEAM_NAME__`, `__SERVICE_NAME__`, `__IMAGE_TAG__` = `source.revision`, `__PORT__` = `runtime.port`, `__HOST__` = `{tenant}-{service}.{PlatformDomain}`), parse into a `yaml.v3` `Node` (key order preserved), then apply in the workflow's order: mirror host (only if `PlatformDomainAlt` is set), cert-manager annotation, `ingress.tls`, probe paths, `env` keys in sorted order, `externalSecret` + `envFrom` for `secretRefs` in input order. The image-USER pin is skipped (needs a built image; item `digest`).
  - **Update**: parse current values with `yaml.v3`; parse error or non-mapping root -> `ErrCurrentValuesInvalid`. Set `image.tag`, sync `extraContainers[].image` with the same repository prefix, merge `env`, merge `externalSecret.data` (dedupe by `secretKey`, the workflow's `+=` after resetting when type is not a sequence) and `envFrom`.
  - **Redaction**: after compiling, replace `externalSecret.data[].remoteKey` and `dbSecret.vaultPath` in both current and after documents with `<derived:vault>`; `diff` is computed over the redacted documents. Since the real path is a pure function of `(tenant, service)`, both bound in the digest, nothing determining the effect is lost.
  - `Diff`: unified diff (3 lines context) of `yaml.v3`-encoded current (empty on onboard) vs after, with a small in-package Myers/LCS line diff (no new dependency).
  - `Host`: first `ingress.hosts` entry of the after document.
- `digest.go`: `const EncodingVersion = "mctl-deploy-plan/v1"`; `Digest(f Fields) string` in exactly the `IntentHash` framing, fields in order `tenant, service, environment, intent, revision, gitops_base_sha, action, values_after, host`.
- `approval.go`: `Requirement(action, environment) Approval` - the risk matrix: onboard -> `{Required: true, Risk: high, RequiredRole: owner, Reason: "first_onboard"}`; update+preview -> `{true, medium, developer, "build_sandbox_pending"}`. Production never reaches it (refused earlier).
- `store.go`: `NewStore(ctx, connStr)` with schema:

```sql
CREATE TABLE IF NOT EXISTS deploy_plans (
    id                    TEXT PRIMARY KEY,           -- dpl_<ULID>
    digest                TEXT NOT NULL,
    schema_version        TEXT NOT NULL,              -- 'deployplan/v1'
    tenant                TEXT NOT NULL,
    service               TEXT NOT NULL,
    environment           TEXT NOT NULL,
    intent                JSONB NOT NULL,             -- canonical form; JSONB for querying,
    intent_canonical      TEXT NOT NULL,              -- exact hashed bytes
    revision              TEXT NOT NULL CHECK (revision ~ '^[0-9a-f]{40}$'),
    gitops_base_sha       TEXT NOT NULL CHECK (gitops_base_sha ~ '^[0-9a-f]{40}$'),
    action                TEXT NOT NULL CHECK (action IN ('onboard','update')),
    values_before_sha256  TEXT NOT NULL DEFAULT '',   -- sha256 of the raw current file; '' on onboard
    values_after          TEXT NOT NULL,              -- redacted rendered YAML
    diff                  TEXT NOT NULL,
    host                  TEXT NOT NULL,
    requires_approval     BOOLEAN NOT NULL,
    required_role         TEXT NOT NULL,
    risk                  TEXT NOT NULL,
    created_by            TEXT NOT NULL,              -- canonical principal (prn_...)
    surface               TEXT NOT NULL,              -- 'rest' | 'mcp'
    idempotency_key       TEXT NOT NULL DEFAULT '',
    created_at            TIMESTAMPTZ NOT NULL,
    expires_at            TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS deploy_plans_idem
    ON deploy_plans (created_by, idempotency_key) WHERE idempotency_key <> '';
CREATE INDEX IF NOT EXISTS deploy_plans_tenant ON deploy_plans (tenant, created_at DESC);
```

  Methods: `Insert(ctx, Plan) (Plan, replayed bool, error)` uses `INSERT ... ON CONFLICT (created_by, idempotency_key) WHERE idempotency_key <> '' DO NOTHING RETURNING ...`; on no row it selects the existing row and returns it if digests match, else `ErrIdempotencyConflict{ExistingID}`. `Get(ctx, id)`. No update or delete method exists (a test reflects over the `Store` method set). `intent` is stored twice on purpose: `intent_canonical` is the hashed text (JSONB normalizes and would not round-trip bytes).
  The store opens its own pool on the work-items database URL (the same `workItemsDBURL` `cmd/api/main.go` passes to `workitems.NewStore`); `pgshared.Open` shares the pool.

### 2. Gitops reader addition

`func (r *Reader) ReadServicePlanInputs(team, component string, templates ...string) (ServicePlanInputs, error)` in `internal/gitops/reader.go`: under one `RLock`, `checkFreshLocked`, `revisionLocked` (must be 40-hex), `statServiceFileLocked` for the directory and `values.yaml` (directory present + file absent -> `ErrServiceDirIncomplete`), read `values.yaml` and `catalog-info.yaml` annotation, and read the named template files under `platform-gitops/argo-workflows/` with the same `Lstat` regular-file discipline. Returns `{BaseSHA, Exists, Values, SourceRepo, Templates map[string][]byte}`. Every non-absence failure is an error.

### 3. Compiler freshness pin

`internal/deployplan/templates.go` pins `sha256` of `argo-workflows/service-templates/default/values.yaml.tpl` and `argo-workflows/cluster-templates/tpl-git-commit.yaml` as vendored under `internal/deployplan/testdata/gitops/`. The handler hashes the live checkout copies from `ReadServicePlanInputs`; a mismatch is 503 `deploy_plan_compiler_stale`. This makes "the Go compiler and the workflow agree" a runtime fail-closed property, not only a test property: when gitops changes the template, plans stop until the vendored copy, the golden fixture and the compiler are updated together.

### 4. REST handlers `internal/api/handlers_deploy_plan.go`

- `DeployPlan` (`POST /api/v1/deploy/plan`, under the same authenticated group as `/deploy/analyze`, with the write rate limiter): body `MaxBytesReader` 256 KiB; strict decode of `{intent, idempotency_key, ttl_seconds}`; `deployplan.ParseIntent`; `production` -> 422 `prod_requires_promote`; `checkTenantRole(user, tenant, operationMinRole("deploy-service", RoleDeveloper), ...)` -> 403; binding check factored out of `DeployAnalyze` into `h.deployRepoBound(ctx, tenant, repo) (services []string, err)` and reused by both handlers; if `SourceRepo` of an existing service differs from `spec.source.repository` -> 403 `deploy_service_repository_mismatch`; `DeployContentReader.Commit` -> 422/502 mapping identical to analyze; `ReadServicePlanInputs`; template pin check; `Compile`; `Digest`; `Requirement`; `Insert`. Response 201 (200 on replay):

```json
{"id":"dpl_...","digest":"sha256:...","schema_version":"deployplan/v1",
 "tenant":"...","service":"...","environment":"preview",
 "revision":"<40hex>","gitops_base_sha":"<40hex>","action":"onboard",
 "host":"t-s.mctl.ai","values_after":"...","diff":"...",
 "approval":{"required":true,"risk":"high","required_role":"owner","reason":"first_onboard"},
 "created_at":"...","expires_at":"...","expired":false,"replayed":false}
```

- `GetDeployPlan` (`GET /api/v1/deploy/plans/{id}`): id must match `^dpl_[0-9A-HJKMNP-TV-Z]{26}$`; not found, or caller neither `HasTenantAccess(plan.tenant)` nor admin -> 404; `expired` computed lazily from the handler's clock.
- Audit via the existing `deployAudit` helper extended with `digest`, `service`, `action` params; operations `deploy.plan` and `deploy.plan.read`.
- `Options` gains `DeployPlans DeployPlanStore` (interface in `internal/api/interfaces.go`) and `PlanGitops DeployPlanGitopsReader`; nil -> 503.

### 5. MCP tools

- `mctl_deploy_plan` (`toolDeployPlan` in `internal/mcp/server.go`): arguments `intent` (object), `idempotency_key`, `ttl_seconds`; posts to `/api/v1/deploy/plan`; added to `governedAgentTools`. Description states that planning writes only the plan record, that `production` is refused, and that the result must be shown to the user before any apply.
- `mctl_get_deploy_plan`: argument `id`; GET; ungoverned (read verb).
- Tool count in `server_test.go` (`TestNewMCPServer_ToolCount`) +2.

### 6. RequiresConfirm becomes load-bearing

- Registry: add `ConfirmWhen map[string][]string` to `Operation` and `func (o Operation) NeedsConfirm(input map[string]string) bool` = `RequiresConfirm || any ConfirmWhen[k] contains input[k]`. Set `deploy-service.ConfirmWhen = {"action": {"onboard"}}`. **Decision: yes, a first onboard is confirm-gated**: it creates a new public host, a new namespace workload and a catalog entry; the spike rates it high. `action=deploy` and `update-config` (and therefore CI deploys through `authorizeCIDeploy`, which deploy onboarded components) stay ungated. Documented in the registry comment and `docs/` operations section of OpenAPI.
- `ExecuteOperation`: after decode and authentication, before `StripUndeclared`, `confirm := input["confirm"]; delete(input, "confirm")`; if `op.NeedsConfirm(input)` (evaluated after defaults so a missing `action` cannot dodge it; `action` is required for deploy-service) and `!strings.EqualFold(strings.TrimSpace(confirm), "yes")` -> audit `denied` and 428 `operation_confirmation_required`. Mode switch `OPERATIONS_CONFIRM_MODE` (`enforce` default, `warn` logs and proceeds) is the rollback lever only.
- MCP: `mctl_create_tenant`, `mctl_provision_database` gain a `confirm` argument and `requireConfirm`; `mctl_deploy_service` gates only when `action == "onboard"`. All confirm-gated tools forward `"confirm": "yes"` instead of deleting it (`retire_service`, `delete_tenant` change from `delete(params, "confirm")` to setting it).
- Parity test `internal/mcp/confirm_parity_test.go`: build the server with a fake API (`httptest.Server`) that records requests; for every registry op where `RequiresConfirm || ConfirmWhen != nil`, look up its tool in an explicit `opTool` map (`create-tenant -> mctl_create_tenant`, ...; the test fails if a confirm-gated op is in neither `opTool` nor an explicit `noMCPTool` list), call it with minimal valid args and no `confirm`, and assert (a) an error result and (b) zero requests reached the fake API; then call with `confirm: "yes"` and assert the forwarded body carries `confirm: "yes"`. For `HandlerOnly` ops the test requires an entry in `handlerConfirmGates` naming the handler test that proves its gate. A companion test in `internal/api/handlers_write_confirm_test.go` iterates the registry and asserts 428 without `confirm` and no `Executor.Submit` call. Mutation proof: the PR description records running the test with the `requireConfirm` line removed from `mctl_retire_service` (red) and restored (green).

### 7. OpenAPI

`internal/openapi/openapi.yaml`: add `/api/v1/deploy/plan` (POST) and `/api/v1/deploy/plans/{id}` (GET) with `DeployPlanRequest`, `DeployPlan`, error codes; document `confirm` and 428 on `/api/v1/operations/{name}/execute`. `embed_test.go` keeps it parseable.

## Alternatives

1. **Store the plan as an `ExecutionRequest` (the manifest's wording).** Dropped: `work_item_execution_requests.work_item_id` is `NOT NULL`, and the type is a claim/lease/fulfil object for the execution platform, which is the shape of an apply. An MCP deploy has no work item. A later item can link the apply's request to `dpl_` ids.
2. **Plan by dry-running `wft-deploy-service` in Argo (a `dry_run` parameter that stops before `git push`).** Exact agreement with the workflow for free, but it needs a cluster round trip of minutes, a pod per plan, a gitops clone with write credentials in reach, and it cannot run in unit tests. The digest would depend on an external process's output. Dropped in favour of a deterministic Go compiler plus a pinned-template fail-closed check and a golden test.
3. **Digest over the whole stored row (or JSON of the response).** Simpler, but binds ids and timestamps, so the same inputs never repeat, and JSON escaping differs between clients. Dropped for the `IntentHash` framing that any client can reproduce.
4. **Make `requires_confirm` a per-operation flag only and add a new `deploy-service-onboard` operation.** Splitting the operation would break the existing `mctl_deploy_service` contract and CI callers. `ConfirmWhen` keeps one operation with a parameter-scoped gate.

## Platform impact

- **Migration**: one new table and two indexes, created idempotently on start (`CREATE TABLE IF NOT EXISTS`), in the work-items database. No change to existing tables. Rows are small (values YAML + diff, typically < 20 KiB); growth bounded by plan creation rate (write rate limiter). Retention sweep is not part of this item; expired rows stay readable as `expired: true`.
- **Backward compatibility**: new routes and tools are additive. The confirmation gate is a **breaking change** for any client that calls the execute route for `create-tenant`, `provision-database`, `retire-service`, `delete-tenant` or `deploy-service action=onboard` without `confirm`. MCP tools in this repo are updated together. External clients (portal, web, Backstage templates) must send `confirm: "yes"`; mitigation: the server accepts and strips `confirm` for every operation from this release, enforcement can be set to `warn` via `OPERATIONS_CONFIRM_MODE` while external callers catch up, and the 428 message names the field.
- **Signup flow**: `handlers_signup.go` uses `guardCustomerTenantCreation`, not the execute route, for its own checks; any portal path that ends in the execute route for `create-tenant` needs `confirm`. To verify in rollout.
- **Security**: the intent schema stays the boundary; compile refuses rather than drops; Vault paths are redacted before storage; a response-scanning test runs `internal/secretscan` style patterns plus `teams/` and `ghp_`/`ghs_`/`github_pat_` over every plan and read response.
- **Risk: Go compiler drifts from the workflow** -> pinned template hashes make plans fail closed (503) instead of silently diverging; the golden test fails on vendored-template change.
- **Risk: gitops HEAD moves between plan and apply** -> `gitops_base_sha` is bound in the digest; the apply item must refuse when HEAD's values differ (`values_before_sha256` is stored for that).
- **Resources**: one GitHub commit read and local file reads per plan; no Argo, no cluster calls.
