# deploy_plan: a server-computed, digest-bound deploy plan, and a load-bearing RequiresConfirm

## Context

Issue mctlhq/mctl-api#866 is work item `plan` of the agent-deploy epic (mctlhq/.github#254). It builds on item `analyze` (mctl-api#826, shipped in 4.130.0 as `internal/deployanalyze`, `GET /api/v1/deploy/analyze` and `GET /api/v1/deploy/bindings`). An AI session that has a DeployIntent, usually the `draft_intent` returned by `mctl_deploy_analyze`, must be able to ask mctl-api for a **plan**: an immutable, server-computed record of exactly what a deploy would change in gitops (the Helm values for `platform-gitops/services/{tenant}/{service}/values.yaml`, the diff against the current values at a pinned gitops commit, the host, and whether this is an onboard or an update), sealed by a digest. A later item (`grants`) binds an approval grant to that digest, so the digest must depend only on what determines the effect. Planning itself changes nothing in gitops or the cluster; the only write is the `deploy_plans` row.

In the same change, `RequiresConfirm` in `internal/operations/registry.go` stops being decorative. Today nothing reads it. Two of the four operations that declare it, `create-tenant` and `provision-database`, have MCP tools (`mctl_create_tenant`, `mctl_provision_database` in `internal/mcp/server.go`) that never call `requireConfirm`, and the generic `POST /api/v1/operations/{name}/execute` (`ExecuteOperation` in `internal/api/handlers_write.go`) takes no confirmation at all. A registry-driven parity test and a server-side gate close that gap. `deploy-service` with `action=onboard` also becomes confirm-gated, because the epic's risk matrix rates a first onboard as high risk.

## User stories

- AS an AI session deploying a repository I WANT to turn a DeployIntent into a stored plan with a diff, host and digest SO THAT a human can see exactly what would change before anything is applied.
- AS a tenant developer I WANT planning the same intent twice to give the same digest SO THAT a later approval binds to a stable, reproducible effect and not to a moving ref or a timestamp.
- AS a platform operator I WANT every plan creation, read and refusal audited, and every failed read reported as an error SO THAT an outage never looks like "onboard" or "no changes".
- AS a platform operator I WANT every operation marked `RequiresConfirm` to actually require confirmation on both the MCP surface and the generic execute route SO THAT the registry flag is a real control, proven by a test that fails when a gate is removed.
- AS a later `grants` / `deploy_apply` implementer I WANT a plan id and digest that cover tenant, service, environment, intent, revision, gitops base SHA, action, compiled values and host SO THAT a grant can be bound to one exact effect.

## Acceptance criteria (EARS)

### Plan creation: input and validation

- WHEN a caller sends `POST /api/v1/deploy/plan` with a body `{"intent": <DeployIntent>, "idempotency_key": <optional string>, "ttl_seconds": <optional integer>}`, or calls the MCP tool `mctl_deploy_plan` with the same arguments, THE SYSTEM SHALL validate `intent` against the vendored schema `internal/deployanalyze/schema/deploy-intent.schema.json` (pinned by `deployanalyze.SchemaSHA256`) before any other read.
- IF the intent fails schema validation (an unknown field, an escape-hatch key such as `extraObjects`, a wrong `apiVersion`/`kind`, a value outside a pattern or range) THEN THE SYSTEM SHALL answer 422 with code `deploy_intent_invalid` and the schema error, and SHALL NOT drop the offending field and continue.
- IF the request body itself has a top-level key other than `intent`, `idempotency_key` and `ttl_seconds`, or `idempotency_key` is longer than 512 bytes, THEN THE SYSTEM SHALL answer 400 with code `deploy_plan_invalid_input`.
- IF `spec.environment` is `production` THEN THE SYSTEM SHALL answer 422 with code `prod_requires_promote` and a message saying production is reached only by promote. (The issue calls this value `prod`; the vendored schema's enum is `preview` | `production`.)
- IF `spec.source.revision` is not a 40-hex lowercase SHA THEN THE SYSTEM SHALL refuse it under `deploy_intent_invalid` (the schema pattern) and SHALL NOT resolve a branch or tag.
- WHEN the revision is well-formed THE SYSTEM SHALL check that the commit exists in `spec.source.repository` through `deployanalyze.ContentReader.Commit` with mctl's GitHub credential.
- IF GitHub answers 404 or 422 for the commit THEN THE SYSTEM SHALL answer 422 with code `deploy_revision_unreadable`.
- IF GitHub fails (5xx, timeout, malformed answer, missing reader) THEN THE SYSTEM SHALL answer 502 with `deploy_github_unavailable` or `deploy_github_malformed`, and SHALL NOT create a plan.
- IF the intent asks for something `deploy-service` cannot write (see design.md "Compilable subset": `exposure.mode: internal`, `resources` that differ from the template, `runtime.replicas` other than 1, a `secretRefs` entry whose `env` differs from its `property`, or on update a `runtime.port` / `runtime.healthPath` that differs from the current values) THEN THE SYSTEM SHALL answer 422 with code `deploy_intent_not_compilable` naming the JSON pointer of the field, and SHALL NOT drop the field.

### Authorization

- WHEN a plan is requested THE SYSTEM SHALL require that the caller has at least the `MinRole` of `deploy-service` (`RoleDeveloper`, read through `operationMinRole("deploy-service", ...)`) on `metadata.tenant`, using the same `checkTenantRole` path as the generic execute route.
- IF the caller is not a member of the tenant, or has a lower role, THEN THE SYSTEM SHALL answer 403 with code `deploy_tenant_access_denied` and audit the refusal.
- IF `spec.source.repository` is not bound to `metadata.tenant` (neither a gitops `github.com/source-repo` binding through `SourceRepoBindingReader.ServicesBySourceRepo` nor a portal binding through `repoBoundToTeam`) THEN THE SYSTEM SHALL answer 403 with code `deploy_repository_not_bound`.
- IF the repository is bound to the tenant only through other services, and `metadata.service` already exists in gitops with a different `github.com/source-repo` THEN THE SYSTEM SHALL answer 403 with code `deploy_service_repository_mismatch`.
- IF the binding cannot be read THEN THE SYSTEM SHALL answer 503 with code `deploy_binding_unavailable` and SHALL NOT treat it as "not bound".

### Compile, action and diff

- WHEN a plan is computed THE SYSTEM SHALL read, under one gitops read lock, the checkout HEAD (`gitops_base_sha`), whether `platform-gitops/services/{tenant}/{service}/values.yaml` exists, its bytes if it does, and the onboard service template, so that every read comes from the same commit.
- WHEN the service directory does not exist at `gitops_base_sha` THE SYSTEM SHALL set `action` to `onboard`. WHEN `values.yaml` exists THE SYSTEM SHALL set `action` to `update`.
- IF the gitops checkout is unsynced, stale (`checkFreshLocked`), unreadable, or a path element is a symlink or non-regular entry THEN THE SYSTEM SHALL answer 503 with code `deploy_gitops_unavailable`, and SHALL NOT answer `action: onboard` or an empty diff.
- IF the current `values.yaml` does not parse as YAML, or parses to something other than a mapping THEN THE SYSTEM SHALL answer 500 with code `deploy_current_values_invalid` and SHALL NOT treat it as "no current values".
- IF the service directory exists but `values.yaml` is absent THEN THE SYSTEM SHALL answer 409 with code `deploy_service_directory_incomplete` rather than plan an onboard over an existing directory.
- IF the live checkout's copies of `argo-workflows/service-templates/default/values.yaml.tpl` or `argo-workflows/cluster-templates/tpl-git-commit.yaml` do not hash to the values pinned in the compiler THEN THE SYSTEM SHALL answer 503 with code `deploy_plan_compiler_stale` and SHALL NOT compile.
- WHEN the action is `onboard` THE SYSTEM SHALL compile `values_after` exactly as `tpl-git-commit`'s onboard branch would for the equivalent `deploy-service` parameters; WHEN the action is `update` THE SYSTEM SHALL compile it exactly as the `deploy` branch would (image tag, same-repository `extraContainers`, merged `env`, merged `externalSecret.data` / `envFrom`).
- THE SYSTEM SHALL return `diff` as a unified diff of the current values (empty for onboard) against `values_after`, and SHALL return `host` as the first `ingress.hosts` entry of `values_after` (on onboard `{tenant}-{service}.{PLATFORM_DOMAIN}`).
- WHILE compiling, THE SYSTEM SHALL write secret references only as names (`secretKey` and `property` from `spec.secretRefs`) and SHALL replace every Vault path the workflow would write (`externalSecret.data[].remoteKey`, `dbSecret.vaultPath`) with the fixed placeholder `<derived:vault>` in both the stored and the returned `values_after` and `diff`.

### Digest

- THE SYSTEM SHALL compute `digest` as `sha256:<hex>` over the encoding `mctl-deploy-plan/v1\n` followed by `<field>:<byte length>:<value>\n` for, in order: `tenant`, `service`, `environment`, `intent` (canonical JSON), `revision`, `gitops_base_sha`, `action`, `values_after`, `host`.
- THE SYSTEM SHALL NOT include the plan id, any timestamp, the TTL, the idempotency key or the caller in the digest.
- WHEN the same inputs are planned twice at the same `gitops_base_sha` THE SYSTEM SHALL produce the same digest; WHEN any one bound field changes THE SYSTEM SHALL produce a different digest.

### Approval requirement

- WHEN `action` is `onboard` THE SYSTEM SHALL set `requires_approval: true`, `risk: high`, `required_role: owner`.
- WHEN `action` is `update` and `environment` is `preview` THE SYSTEM SHALL set `requires_approval: true`, `risk: medium`, `required_role: developer`, with reason `build_sandbox_pending`, until item `preconditions` lands.
- THE SYSTEM SHALL name the required approval in the response (`approval: {required, risk, required_role, reason}`) and SHALL NOT create or check any grant.

### Store, read, expiry and idempotency

- WHEN a plan is created THE SYSTEM SHALL insert exactly one row into `deploy_plans` with an id of the form `dpl_<ULID>`, and SHALL have no UPDATE or DELETE path for that table in this item.
- WHERE `ttl_seconds` is given it SHALL be between 60 and 86400; otherwise THE SYSTEM SHALL use 1800 (30 minutes).
- WHEN a caller sends `GET /api/v1/deploy/plans/{id}` or calls `mctl_get_deploy_plan` THE SYSTEM SHALL return the stored plan, its digest and `expired` computed as `now >= expires_at`. `expired` is never stored.
- IF the caller is neither a member of the plan's tenant nor a platform admin THEN THE SYSTEM SHALL answer 404 `deploy_plan_not_found`, exactly as for an id that does not exist.
- WHEN the same `(created_by, idempotency_key)` is used again and the recomputed digest equals the stored one THE SYSTEM SHALL return the stored plan with `replayed: true` and HTTP 200.
- IF the same `(created_by, idempotency_key)` is used with a different digest THEN THE SYSTEM SHALL answer 409 `deploy_plan_idempotency_conflict` naming the stored plan id.
- IF the plan store is not configured or not reachable THEN THE SYSTEM SHALL answer 503 `deploy_plan_store_unavailable`.

### No leakage

- THE SYSTEM SHALL NOT return, store, log or audit any secret value, Vault path, GitHub token, image pull credential or `secret_env_secret` name in any plan response.

### Audit

- WHEN a plan is created, read, replayed or refused THE SYSTEM SHALL write one audit entry with operation `deploy.plan` or `deploy.plan.read`, the caller, tenant, service, digest (when known) and outcome (`succeeded`, `replayed`, `denied:<code>`, `error:<code>`).

### RequiresConfirm becomes load-bearing

- WHEN an operation is `RequiresConfirm: true`, or its `ConfirmWhen` matches the input (for `deploy-service`: `action=onboard`), and it is submitted through `POST /api/v1/operations/{name}/execute` without a body key `confirm` equal to `yes` (case-insensitive, trimmed) THE SYSTEM SHALL answer 428 with code `operation_confirmation_required`, audit the refusal, and SHALL NOT submit a workflow.
- WHEN the generic execute route reads `confirm` THE SYSTEM SHALL remove it from the input before `StripUndeclared`, so it never reaches Argo.
- WHEN an MCP tool submits a confirm-gated operation THE SYSTEM SHALL gate on `requireConfirm` in the tool and forward `confirm: "yes"` to the execute route. This adds the gate to `mctl_create_tenant`, `mctl_provision_database` and `mctl_deploy_service` (onboard only), which have none today.
- WHILE an operation is `HandlerOnly`, THE SYSTEM SHALL accept it in the parity test only if its dedicated handler is listed with its own confirmation gate.
- THE SYSTEM SHALL have a registry test that fails when any confirm-gated operation's MCP tool does not gate on confirmation, or when the execute route accepts it without `confirm`.

## Out of scope

- Grants, `deploy_apply` and replacing `confirm="yes"` with server-held grants (item `grants`).
- Image digests, building the image, and pinning `containerSecurityContext.runAsUser` from the image USER (item `digest`; the pin depends on the built image and is excluded from `values_after`).
- Health gate, DeployRecord, rollback, preview-before-onboard, promote and every `production` plan (later items of #254).
- Compiling the preview Helm overlay (`helm --set` of `wft-preview-deploy`: preview id, preview host). The preview id is minted at apply time.
- `provision_database`, autoscaling and `config_patch` (not expressible in DeployIntent v1alpha1).
- Switching mctl-agents `resolve_deploy_target` (mctl-agents#834).
- Correcting the epic manifest title (done in the PR that binds this issue in mctlhq/.github).

## Open questions

- **Which environment does a plan in this item target?** The issue refuses `production` but `deploy-service` writes only `platform-gitops/services/{tenant}/{service}/values.yaml`, which ArgoCD syncs to the tenant's production namespace; `wft-preview-deploy` reads that same file and overlays a preview id and host at apply time. This proposal plans the base values file for `environment: preview`, binds `environment` in the digest, and leaves the preview overlay to the apply item. If the author intends `production` onboard plans to be allowed (and only production updates refused), the refusal rule changes. Filed as the one clarification question.
- **Image tag.** DeployIntent has no image field and `deploy-service` derives `image.tag` from `git_tag`. This proposal compiles `image.tag` as the full 40-hex `source.revision`, which the apply item must build under. Item `digest` may replace it.
- **Env and secret semantics on update.** `tpl-git-commit` merges `env` and `externalSecret.data` on `deploy`; it cannot clear and set in one run. This proposal plans merge semantics, so keys present today and absent from the intent are kept and shown as unchanged in the diff.
- **`exposure.mode: internal`.** With `base-service` an empty host is auto-generated, so `internal` cannot be produced by `deploy-service` today; it is refused as `deploy_intent_not_compilable`. A later item may map it to `worker-service` or `ingress.enabled: false`.
- **External callers of the execute route.** mctl-portal, mctl-web or Backstage may call `create-tenant` / `provision-database` / `deploy-service onboard` through the generic execute route without `confirm`. They are not in this repository; they must send `confirm: "yes"` before enforcement ships. `OPERATIONS_CONFIRM_MODE=warn` exists only as the rollback switch.
- **Required role of the onboard approval.** `required_role: owner` for onboard is an interpretation of "high risk"; the issue does not name a role.
