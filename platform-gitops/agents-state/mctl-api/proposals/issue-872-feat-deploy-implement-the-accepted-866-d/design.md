# Design: issue-872-feat-deploy-implement-the-accepted-866-d

This design carries over the accepted #866 design (mctl-gitops `platform-gitops/agents-state/mctl-api/proposals/issue-866-feat-deploy-deploy-plan-with-a-server-co/design.md` at `f23603ca`) unchanged in substance. The only changes are the retry framing, anchors re-verified against this clone, and a fresh deployed-state list. If this file and the #866 design ever disagree, the #866 design wins, and the implementer records the mismatch in the PR.

## Current state

**Retry context.** The #866 implement attempt (`.status.yaml` at `f23603ca`: `status: needs-triage`, `failure.code: no-commits`, `stop_reason: no_commits`, `verification.required_passed: 0/4`) produced no commits because it tried to reach mctl-gitops. Two things now remove that need, both read in this clone (HEAD `0696dbd`, "Merge pull request #870"):
- `internal/deployplan/` exists with only `doc.go` (the package comment for the #866 package) and `upstream_test.go`. The test loads `testdata/upstream/provenance.json`, confines reads with `os.OpenRoot`, and requires the three snapshots `wft-preview-deploy.yaml`, `tpl-git-commit.yaml` and `rewrite_preview_values.py` with their SHA-256s.
- `provenance.json` pins `source_repo: mctlhq/mctl-gitops`, `source_commit: 7cdfb659592d3e9d595cd2c6406b4fde3dad1b24`, and `refresh: scripts/refresh-deployplan-upstream.sh`. That script exists in `scripts/`. The CI step "deploy-plan upstream drift" in `.github/workflows/validate.yml` (line 78) compares the snapshots with mctl-gitops main. Everything the golden tests need is inside the clone.

**Anchors re-verified in this clone** (the #866 line numbers still hold):
- `internal/api/router.go:594-595`: the `/deploy/analyze` and `/deploy/bindings` routes.
- `internal/api/handlers_write.go:51`: `ExecuteOperation`, with `StripUndeclared` at line 115. Nothing in that file reads `RequiresConfirm`.
- `internal/operations/registry.go:45`: the `RequiresConfirm` field. It is `true` at lines 471, 508, 522 and 538; every other operation, including `deploy-service` at 437, is `false`.
- `internal/mcp/server.go:2732`: `requireConfirm`. It gates `mctl_retire_service` (1285) and `mctl_delete_tenant` (1334). `mctl_create_tenant` posts at 898 and `mctl_provision_database` at 1097, and neither is gated.
- `internal/api/tenant_role.go:235,251`: `requireTenantRole` and `operationMinRole`.
- `internal/workitems/action_approvals.go:63`: `intentEncodingVersion = "mctl-action-intent/v1"`.
- `internal/surfaceid/` exists (`store.go`) and is the source for the `surface` column.
- `internal/gitops/reader.go`: `checkFreshLocked` (756), `ServiceExists` (834), `statServiceFileLocked` (858), `Revision` (1184), `ReadFiles` (1201) and `ComponentSourceRepo` (1250).
- `cmd/api/main.go:613-623` and `2529-2538`: the work-items store, sourced from `WORK_ITEMS_DB_URL`, else `AUDIT_DB_URL`, with the `WORK_ITEMS_DISABLED` kill switch.
- `internal/api/handlers_signup.go:485`: the signup path calls `guardCustomerTenantCreation` with `operations.Operation{Name: "create-tenant"}` directly and never goes through `ExecuteOperation`, so the 428 gate does not affect it (task 10 in-repo row).
- The MCP tool count is `len(recordedHints)` (`internal/mcp/annotations_test.go:28`, checked in `server_test.go:174` and `stateless_test.go:81`). Adding the two tools means adding two `recordedHints` entries.
- `go.mod` requires `gopkg.in/yaml.v3 v3.0.1` directly. `github.com/pmezard/go-difflib` appears only in `go.sum` (indirect via testify).

The rest of this section is the #866 current-state description. It is still accurate for this clone.

**Analyze (the dependency).** `internal/api/handlers_deploy_analyze.go` serves `GET /api/v1/deploy/analyze` and `GET /api/v1/deploy/bindings` (routes in `internal/api/router.go:594-595`).
- `DeployAnalyze` validates input with `deployTenantRe`, `validDeployRepo`, `deployRevRe` (`^[0-9a-f]{40}$`) and `validDeployPath`.
- It checks `user.HasTenantAccess(tenant)` only. It does not check the operation's `MinRole`.
- It resolves the binding through `SourceRepoBindingReader.ServicesBySourceRepo` (gitops `github.com/source-repo` annotation), with `h.repoBoundToTeam` (portal) as fallback.
- It calls `deployanalyze.Analyze` with `h.opts.DeployContentReader` and maps `ErrRevisionUnreadable` to 422, and `ErrGitHubMalformed` and `ErrGitHubUnavailable` to 502.
- It writes one audit row through the `deployAudit` helper (`refuse`, `set`, `write`).

**DeployIntent schema.** `internal/deployanalyze/schema.go` embeds `schema/deploy-intent.schema.json`, pinned by `SchemaSHA256`, and exposes `Validate(map[string]any)`.
- The schema is closed (`additionalProperties: false` at every level).
- `spec.environment` is `preview | production`. `source.revision` must match `^[0-9a-f]{40}$`.
- `runtime` has `port` (1024-65535), `healthPath` and `replicas` (1-3). `resources.{requests,limits}` and `exposure.mode` (`internal | public`) follow.
- `env` is a map of plain values. `secretRefs[]` is `{env, property}`, and the Vault path is derived, never supplied.

**GitHub reader.** `internal/deployanalyze/github.go`: `ContentReader.Commit(ctx, repo, sha)` returns `ErrRevisionUnreadable` on 404/422, `ErrGitHubUnavailable` on other statuses, and `ErrGitHubMalformed` when the SHA does not echo back.

**Gitops reader.** `internal/gitops/reader.go` keeps a local checkout.
- `Revision()` returns `r.head`.
- `ReadFiles` reads files and the revision under one `RLock`, so they are one checkout.
- `ServiceExists` and `statServiceFileLocked` walk `platform-gitops/services/<team>/<component>/<file>` with `Lstat`: a missing element below `services/` means absent, while a symlink, a non-plain entry or a missing `services/` directory is an error.
- `checkFreshLocked` refuses a stale checkout.
- `ComponentSourceRepo` reads the source-repo annotation and fails closed (`ErrSourceRepoNotRegistered` only for a read checkout without it).

**Preview apply (what a preview plan must describe).** `platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml` (read in `$MCTL_GITOPS_ROOT`), lines 400-478:
- `PREVIEW_ID` is the last 6 `[a-z0-9]` characters of the Argo workflow name. `HOST` is `${COMPONENT}-${PREVIEW_ID}.${PLATFORM_DOMAIN}`.
- The template clones gitops HEAD and runs `scripts/rewrite_preview_values.py` over the service `values.yaml`. This moves `teams/<t>/<s>/...` Vault paths to `teams/<t>/<s>/preview/...`, forces team ExternalSecrets and `dbSecret` onto `tenant-store`/`SecretStore`, and refuses mixed platform/team keys and paths outside `teams/<t>/`.
- It then runs `helm upgrade --install` with fixed `--set` overrides:
  - `image.tag`
  - `ingress.enabled=true`, `ingress.className=traefik`, the cert-manager issuer annotation, `ingress.hosts={HOST}`, `ingress.tls[0]`
  - `blueGreen.enabled=false`, `dbInitJob.enabled=false`
  - optional `service.port`
  - `podLabels.mctl.ai/preview=true`, `podLabels.mctl.ai/preview-id`

  Nothing is written to gitops.

**Production write path (for the intent-to-values mapping).** `argo-workflows/cluster-templates/tpl-git-commit.yaml` (lines 405-640) applies the deploy-service parameters to `values.yaml` with yq:
- `.probes.liveness.path` and `.probes.readiness.path` from `HEALTH_CHECK_PATH`
- `.env[KEY] = VALUE`
- `.externalSecret.targetSecret` and `.externalSecret.data += {secretKey, remoteKey: teams/<t>/<s>, property}`

The base chart keys are in `helm-charts/base-service/values.yaml` (`replicaCount`, `resources`, `service.port`, `probes`, `env`, `externalSecret`, `ingress`, ...).

**Operations registry.** `internal/operations/registry.go:45` declares `RequiresConfirm`. The `true` operations are `create-tenant`, `provision-database`, `retire-service` and `delete-tenant`. `deploy-service` is `RequiresConfirm: false`, `RiskMedium`, `MinRole: RoleDeveloper`.
- `ExecuteOperation` (`internal/api/handlers_write.go:51`) never reads `RequiresConfirm`. It decodes the body as `map[string]string` and calls `Registry.StripUndeclared`, so a `confirm` key would be dropped today.
- In `internal/mcp/server.go`, `requireConfirm` (line 2732) gates `mctl_retire_service` (1285) and `mctl_delete_tenant` (1334). It does **not** gate `mctl_create_tenant` (836, posts at 898) or `mctl_provision_database` (1069, posts at 1097). All four post to `/api/v1/operations/<op>/execute`.
- No operation with `RequiresConfirm: true` is `HandlerOnly`.

**Stores.** `internal/workitems/store.go` keeps its DDL in a `const schema` of `CREATE TABLE IF NOT EXISTS` statements, applied by `NewStore` over `pgshared.Open`. `cmd/api/main.go:611-640` wires it from `WORK_ITEMS_DB_URL` or `AUDIT_DB_URL` (kill switch `WORK_ITEMS_DISABLED`). A nil store makes routes answer 503. `internal/workitems/action_approvals.go:63` has `intentEncodingVersion = "mctl-action-intent/v1"`, a versioned, length-prefixed canonical encoding that this design copies.

**Authorization helpers.** `requireTenantRole` and `operationMinRole` are in `internal/api/tenant_role.go:235,251`. The roles are `viewer`, `developer`, `owner` and `admin` (`internal/operations/roles.go`). `auth.User.PrincipalID()` returns the canonical principal (`internal/auth/principal.go:115`).

Deployed state checked:
- `mctl_list_services(team=admins)`: `complete: true`, 8 catalogue services (mctl-agents-worker, mctl-agents-worker-exec, mctl-agents-worker-implement, mctl-design, mctl-docs, mctl-support, mctl-web, umami). mctl-api is not a catalogue tenant service, so this tool could not show its runtime config (DB URL, `PlatformDomain`). The design relies on the code defaults in `cmd/api/main.go`, the same as #866.
- `$MCTL_GITOPS_ROOT/services/`: tenants `admins`, `karabu`, `labs`, `namax66`. No `services/*/mctl-api` directory, which is consistent with the above.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-866-feat-deploy-deploy-plan-with-a-server-co/` (checkout HEAD `f23603ca`, "Merge pull request #2281 ... amend-api866-callers-fixtures"): `requirements.md`, `design.md`, `tasks.md` read in full and `.status.yaml` read (approval by mashkovd 2026-10-30T12:05:26Z, needs-triage, no-commits). This is the authoritative spec this proposal carries over.
- Not checked: the live `deploy_plans` table (it does not exist yet), and the live database behind `WORK_ITEMS_DB_URL`/`AUDIT_DB_URL` (not observable with read-only tools). Neither is needed to implement.

## Proposed solution

### 1. New package `internal/deployplan`

The package is pure and deterministic. It does no I/O except through interfaces.

- `types.go`
  - `Plan` struct holding every stored column.
  - `Action` constants: `ActionUpdate`, plus `ActionOnboard` reserved and never produced in this item.
  - `Approval{Required bool, Role string, Reason string}`.
- `intent.go`: `ParseIntent(raw json.RawMessage) (Intent, map[string]any, error)`.
  - It decodes with `UseNumber`, refuses duplicate keys and validates with `deployanalyze.Validate`.
  - It decodes into a typed `Intent` with `DisallowUnknownFields`, as a second guard.
  - It returns the canonical intent JSON: sorted keys, no insignificant whitespace, with the schema defaults `dockerfile: Dockerfile`, `context: .` and `replicas: 1` made explicit. A caller that omits a default and one that spells it out therefore get the same digest.
- `compile.go`: `CompilePreview(base []byte, in Intent, previewID, host string) (before, after map[string]any, err error)`.
  1. Parse `base` with `yaml.v3` into `map[string]any`. A non-mapping document or a parse error returns `ErrValuesUnparseable`.
  2. `effective(base, nil)` gives the "before" values: the preview rewrite plus the fixed overrides applied to base, with no intent changes.
  3. `effective(base, in)` gives the "after" values. First apply the intent the way `tpl-git-commit` does:
     - `.service.port = runtime.port`
     - `.probes.liveness.path` and `.probes.readiness.path` = `runtime.healthPath`
     - `.replicaCount = runtime.replicas`
     - `.resources` = `spec.resources`, when present
     - `.env[k] = v` for each `spec.env` entry (merge, as `tpl-git-commit` does without `clear_env`)
     - `.externalSecret.targetSecret = {service}-secrets`
     - `.externalSecret.data` upserted by `secretKey` with `{secretKey: env, remoteKey: teams/{tenant}/{service}, property}`

     Then apply the Go port of `rewrite_values` (`rewriteRemoteKey`, `classifyKeys`, `forceTenantStore`, `dbSecret`). Mixed keys or foreign paths return `ErrPreviewValuesRefused`.

     Then apply the `helm --set` overrides of `wft-preview-deploy`:
     - `image.tag = "rev-" + revision`
     - `ingress.enabled: true`, `className: traefik`, `annotations["cert-manager.io/cluster-issuer"] = letsencrypt-prod`, `hosts = [host]`
     - `tls = [{secretName: preview-{service}-{id}-tls, hosts: [host]}]`
     - `blueGreen.enabled: false`, `dbInitJob.enabled: false`
     - `podLabels["mctl.ai/preview"] = "true"`, `podLabels["mctl.ai/preview-id"] = id`

     `exposure.mode: internal` still gets the preview ingress, because the preview template always enables it. This is recorded as an open question.
- `redact.go`: `Redact(values) map[string]any`.
  - It replaces every `externalSecret.data[].remoteKey`, `extraExternalSecrets.*.data[].remoteKey` and `dbSecret.vaultPath` with `redacted:sha256:<hex(path)>`.
  - Kubernetes secret names (`imagePullSecrets[].name`, `envFrom[].secretRef.name`, `externalSecret.targetSecret`) are kept, because a name is not a credential. Only the path-bearing keys are redacted.
  - `values_after`, `diff` and `values_before_sha256` are computed from redacted maps only. The digest is computed over the redacted `values_after`, which still binds the real paths through their hashes.
- `render.go`: canonical YAML rendering (sorted keys, `yaml.v3` with a fixed indent) and `UnifiedDiff(before, after string)`. The diff uses a small deterministic LCS-based line diff, or `github.com/pmezard/go-difflib` if it is already in `go.sum`. The implementer checks `go.mod` and adds no new dependency when an equivalent is vendored.
- `previewid.go`: `PreviewID(tenant, service, revision, gitopsBase string) string`. It takes the first 6 characters of base32-lower(sha256(`mctl-preview-id/v1\x00` + fields)) and maps them to `[a-z0-9]`. `Host(service, id, platformDomain)` builds the host.
- `digest.go`: `const encodingVersion = "mctl-deploy-plan/v1"`. `Digest(p DigestInput) string` writes the version, then each field as `len:value\n` in the fixed order tenant, service, environment, canonical_intent, revision, gitops_base_sha, action, preview_id, values_after (canonical YAML of the redacted map), host. It returns `"sha256:" + hex`. This mirrors `intentEncodingVersion` in `action_approvals.go`.
- `approval.go`: `RequiredApproval(env string, action Action) Approval` holds the risk matrix:
  - preview update gives `{true, "owner", "preview_update_requires_approval_until_build_sandbox"}`
  - onboard (unreachable here) gives `{true, "owner", "onboard_high_risk"}`
- `store.go`: a `Store` using `pgshared.Open`, with the DDL as a `const schema` in the workitems style:

```sql
CREATE TABLE IF NOT EXISTS deploy_plans (
  id                   TEXT PRIMARY KEY CHECK (id LIKE 'dpl\_%'),
  digest               TEXT NOT NULL CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
  schema_version       TEXT NOT NULL,          -- 'mctl-deploy-plan/v1'
  tenant               TEXT NOT NULL,
  service              TEXT NOT NULL,
  environment          TEXT NOT NULL CHECK (environment = 'preview'),
  intent               JSONB NOT NULL,          -- canonical intent
  intent_canonical     TEXT NOT NULL,           -- exact bytes digested
  revision             TEXT NOT NULL CHECK (revision ~ '^[0-9a-f]{40}$'),
  gitops_base_sha      TEXT NOT NULL CHECK (gitops_base_sha ~ '^[0-9a-f]{40}$'),
  action               TEXT NOT NULL CHECK (action IN ('onboard','update')),
  preview_id           TEXT NOT NULL,
  values_before_sha256 TEXT NOT NULL,
  values_after         TEXT NOT NULL,           -- redacted canonical YAML
  diff                 TEXT NOT NULL,
  host                 TEXT NOT NULL,
  requires_approval    BOOLEAN NOT NULL,
  required_role        TEXT NOT NULL,
  approval_reason      TEXT NOT NULL,
  created_by           TEXT NOT NULL,           -- canonical principal
  surface              TEXT NOT NULL,           -- 'rest' | 'mcp'
  idempotency_key      TEXT,
  created_at           TIMESTAMPTZ NOT NULL,
  expires_at           TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at
                         AND expires_at <= created_at + interval '24 hours')
);
CREATE UNIQUE INDEX IF NOT EXISTS deploy_plans_idem
  ON deploy_plans (created_by, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS deploy_plans_tenant ON deploy_plans (tenant, created_at DESC);
CREATE OR REPLACE FUNCTION deploy_plans_immutable() RETURNS trigger
  LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'deploy_plans rows are immutable'; END $$;
DROP TRIGGER IF EXISTS deploy_plans_no_update ON deploy_plans;
CREATE TRIGGER deploy_plans_no_update BEFORE UPDATE ON deploy_plans
  FOR EACH ROW EXECUTE FUNCTION deploy_plans_immutable();
```

  - Methods: `Insert(ctx, *Plan) (stored *Plan, replayed bool, err error)` and `Get(ctx, id) (*Plan, error)`.
  - There is no Update method.
  - `Insert` runs `INSERT ... ON CONFLICT (created_by, idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING RETURNING *`. When nothing is returned it reads the existing row: the same digest is a replay, and a different digest is `ErrIdempotencyConflict`.
  - Ids are `dpl_` + ULID, in the style of the existing work-item ids.
  - The `surface` value is reused from `internal/surfaceid` if it has a constant set; otherwise it is `rest` or `mcp`, taken from the auth context the way work items record it.

### 2. Gitops reader: one consistent read

`internal/gitops/reader.go` gets `ServiceValuesAt(team, component string) (data []byte, sourceRepo string, exists bool, rev string, err error)`.
- It holds `RLock` once and calls `checkFreshLocked`, `revisionLocked` and `statServiceFileLocked(team, component, "values.yaml")`.
- `""` from the stat means `exists=false` (documented absence). Otherwise it reads the file and `sourceRepoLocked` and returns all of them with the same `rev`.
- Every other failure is an error.
- `api.Options` gets an interface `DeployPlanGitops` holding this method, so tests inject fakes.

### 3. REST handler `internal/api/handlers_deploy_plan.go`

`POST /api/v1/deploy/plan` and `GET /api/v1/deploy/plans/{id}` are registered next to the analyze routes in `router.go`. The handler reuses `deployAudit`, with params taken from the decoded intent instead of the query.

Order of checks (each refusal is audited):
1. Authenticate.
2. Decode the body (`http.MaxBytesReader` 256 KiB, `DisallowUnknownFields` on the envelope), giving 400.
3. Check the revision shape (`deployRevRe`) before schema validation, so a ref gets the specific code `deploy_revision_not_a_sha` (422). Then `deployplan.ParseIntent` (422 `deploy_intent_invalid`).
4. `environment == production` gives 422 `prod_requires_promote`.
5. `requireTenantRole(..., operationMinRole("deploy-service", RoleDeveloper), "deploy.plan", RiskLow)`.
6. Repository binding: a factored helper `h.deployRepoBound(ctx, tenant, repo)` extracted from `DeployAnalyze`, which then calls the same helper. Unbound gives 403 and unreadable gives 503.
7. `DeployContentReader.Commit`, mapped exactly like analyze.
8. `ServiceValuesAt`:
   - error gives 503 `deploy_gitops_unavailable`
   - `!exists` gives 422 `onboard_requires_preview_onboard`
   - an annotation that is not the intent's repository gives 403 `deploy_service_not_bound`
9. `PreviewID`, `Host(PlatformDomain)`, then `CompilePreview`:
   - unparseable values give 500 `deploy_values_unparseable`
   - a refused rewrite gives 422 `deploy_preview_values_refused`
10. Redact, render, diff, `Digest`, `RequiredApproval`.
11. `Store.Insert`:
    - no store gives 503 `deploy_plan_store_unavailable`
    - an idempotency conflict gives 409
12. Respond 201, or 200 with `replayed: true`.

The response shape is the plan plus `expired` and `approval`.

`GET` loads the plan and returns 404 unless `user.IsAdmin() || user.HasTenantAccess(plan.Tenant)`. A non-member gets 404, not 403, so ids do not leak existence.

### 4. MCP tools `internal/mcp/deploy_plan.go`

- `mctl_deploy_plan(intent object, idempotency_key?, ttl_seconds?)` posts to the REST route.
- `mctl_get_deploy_plan(id)` gets from the REST route.
- Both descriptions say that planning changes nothing, that production and onboard are refused, and that approval is a later step.
- Both are registered in `server.go`, and the tool-count expectation in `server_test.go` goes up by 2.

### 5. RequiresConfirm made load-bearing

- **Generic route.** In `ExecuteOperation`, after decoding the body and before `StripUndeclared`:

  ```go
  if op.RequiresConfirm && !confirmed(input["confirm"]) {
      h.auditConfirmRefusal(...)
      writeErrorCode(w, 428, "operation_confirmation_required", ...)
      return
  }
  delete(input, "confirm")
  ```

  This means `confirm` never reaches Argo or the undeclared-parameter warning. `confirmed` uses the same rule as the MCP `requireConfirm`: trimmed, case-insensitive `yes`.
- **MCP.** `mctl_create_tenant` and `mctl_provision_database` gain a `confirm` parameter and a `requireConfirm` gate before `apiPost`. All four tools set `params["confirm"] = "yes"` after the gate.
- **Map.** `internal/mcp/operation_tools.go` holds `var operationTools = map[string]string{"create-tenant": "mctl_create_tenant", ...}`, the declared mapping from registry operation to MCP tool. The parity test (task 11) uses it, and a source-scan test asserts that every `apiPost(ctx, "/api/v1/operations/<op>/execute"` literal in the package names an operation present in the map, so a new tool cannot escape the parity test.
- **deploy-service onboard decision.** It stays `RequiresConfirm: false`. A comment on the registry entry records the reasons:
  - The flag is per operation, and `action=deploy` is the unattended CI OIDC auto-deploy path (`authorizeCIDeploy`), which has no human to confirm.
  - First onboard is high risk. It is now refused at plan time (`onboard_requires_preview_onboard`), and its gate is the server-held grant of item `grants`, not `confirm="yes"`.
  - A per-action confirm would need a registry schema extension that `grants` supersedes.

### 6. OpenAPI

`internal/openapi/openapi.yaml` gets:
- the two paths, the `DeployPlanRequest`, `DeployPlan` and `DeployPlanApproval` schemas, and every error code above
- `confirm` on the generic execute body, with the 428 response

## Alternatives

1. **Store the plan as a work-item ExecutionRequest (the epic manifest's wording).** Rejected, as the issue explains. `work_item_execution_requests.work_item_id` is `NOT NULL`, an MCP deploy has no work item, and an ExecutionRequest is a claim/lease/fulfil object, which is the shape of apply.
2. **Compile the production base values file and leave the preview overlay to apply.** Rejected by the owner decision of 2026-10-30. A preview plan would digest an effect it never has, and a grant bound to it would approve the wrong thing.
3. **Shell out to `rewrite_preview_values.py` and `helm template` at plan time.** Rejected. It needs Python and helm in the mctl-api image, a gitops chart checkout and process execution on the request path, and it is harder to make deterministic and fail closed. A Go port plus a golden test against fixtures captured from the real script and template gives the same guarantee without runtime dependencies.
4. **Use the Argo-derived preview id at apply time and leave host out of the digest.** Rejected. `host` is a bound field in the issue, and an unbound host would let apply expose a different hostname than the one approved.
5. **Re-investigate and redesign #866 for the retry.** Rejected. The spec is owner-approved and amended. A redesign would invalidate the approval digest and repeat the decision of 2026-10-30. The failure was environmental (no reach to other repositories), not a design defect.
6. **Read the mctl-gitops files directly in golden tests or at build time.** Rejected. That is what made the #866 run fail. The pinned snapshots in `testdata/upstream/` are the inputs, and CI drift detection keeps them honest.

## Platform impact

- **Migration.** There is one new table, `deploy_plans`, plus an index, a unique partial index and an immutability trigger. All are `IF NOT EXISTS` / `CREATE OR REPLACE` and idempotent on restart. The table lives in the work-items database (same `WORK_ITEMS_DB_URL`/`AUDIT_DB_URL` source and `WORK_ITEMS_DISABLED` kill switch, wired in `cmd/api/main.go`). With no DB, both deploy-plan routes answer 503. Nothing else changes.
- **Backward compatibility.**
  - The new routes and tools are additive.
  - `DeployAnalyze` behaviour is unchanged by the binding-helper extraction (its existing tests stay green).
  - **Breaking:** the generic execute route now answers 428 for `create-tenant`, `provision-database`, `retire-service` and `delete-tenant` without `"confirm": "yes"`. MCP tools are updated in the same change. External REST callers must be audited (task 10), and the enforcement ships only after every affected caller is compatible or its fix is merged and deployed (or ships atomically with it); an open companion PR does not satisfy the gate. Rollout order: client compatibility -> clients merged and deployed -> mctl-api 428 enforcement. No warn-only mode is added: with this gate enforcement goes live at once, and the narrow rollback is reverting only the `ExecuteOperation` gate commit. The signup path (`handlers_signup.go`) submits through its own guard and is checked by the same task.
- **Resources.** A plan costs one GitHub commit read, one local file read and an in-memory compile of a values file of at most a few KiB. Bodies are capped at 256 KiB. Rows are small (two YAML texts). There is no cleanup job in this item. Rows are immutable and small, and retention can be added later.
- **Risks and mitigations.**
  - **Go compiler drift from the workflow template or script.** The golden test uses the upstream snapshots already in mctl-api under `internal/deployplan/testdata/upstream/` (merged in mctlhq/mctl-api#870: `provenance.json` pins source commit and SHA-256, `scripts/refresh-deployplan-upstream.sh` is the only update path, and the `validate.yml` step "deploy-plan upstream drift" fails when they differ from mctl-gitops main). They are test fixtures, not a second source of truth: the implementer reads them from the mctl-api clone, never from mctl-gitops, and never edits them by hand. It extracts the `--set` keys and yq assignment paths and compares them with the Go compiler's declared key set. A re-vendored template with changed keys turns the test red.
  - **Secret leakage.** Redaction is applied before render. A response-scanning test asserts no `teams/`, `secret/data/`, `vault`, `ghp_`, `gho_`, `ghs_` or env-secret value appears.
  - **Fail-open on read errors.** Each of the onboard/update, revision-exists and requires_approval decisions has a converged-fixture test and a mutated-fixture test.
  - **Plan/apply preview id mismatch until apply exists.** This is documented. Apply is a later item.
- **Retry risk.** The implementer could stall again by trying to reach mctl-gitops for the fixtures or the caller audit. Mitigation: tasks 0 and 10 state that both are inside the clone, and that the implementer must not leave the clone.
