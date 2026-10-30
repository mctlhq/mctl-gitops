# deploy_plan: a server-computed, immutable preview plan with a digest; RequiresConfirm becomes load-bearing (retry of #866)

## Context

Issue mctlhq/mctl-api#866 is the `plan` work item of the agent-deploy epic (mctlhq/.github#254). It builds on `analyze` (mctl-api#826, `internal/deployanalyze`, `GET /api/v1/deploy/analyze`). An AI session that has a DeployIntent (the `draft_intent` that `mctl_deploy_analyze` returns, possibly edited) needs to learn exactly what a deploy would change, before anything changes. That answer must be computed by the server, stored immutably, and identified by a digest that a later grant (item `grants`) can bind to. Planning writes nothing to gitops or the cluster. The only write is one `deploy_plans` row.

The owner decision of 2026-10-30 (answer to `hir-68f2286fbe277c65`) narrows the item. A plan is a **preview** plan. It compiles, diffs and digests the effective preview Helm values. These are the base `platform-gitops/services/{tenant}/{service}/values.yaml` read at a pinned gitops SHA, run through the same preview rewrite `wft-preview-deploy` applies (`rewrite_preview_values.py` plus its `helm --set` overrides), with the intent-derived changes, the preview id and the preview host. The plan never writes to or digests the base file as its own effect. `environment: production` is refused (`prod_requires_promote`). A service whose directory is absent at the pinned SHA is refused (`onboard_requires_preview_onboard`), so `action` is always `update` in this item. In the same change, `RequiresConfirm` in `internal/operations/registry.go` stops being decorative: the generic execute path and every MCP tool for such an operation gate on it, and a parity test proves this.

This proposal is the retry of the accepted #866 proposal, carried by mctlhq/mctl-api#872. It is not a redesign. The DevLoop on #866 (`dev-loop-mctlhq-mctl-api-866`) ended Failed after implement with `failure.code: no-commits` (attempt `ec624b75...`, run `mctl-agents-implement-62d43db3`), because the implementer could not reach other repositories. A loop that failed after implement cannot be restarted on the same issue (mctlhq/mctl-agents#748). The specification below is the owner-approved, amended #866 proposal on mctl-gitops main at `f23603ca` (approval digest `sha256:3fb192fa...`), carried over unchanged in substance. Two things changed since that run, and both are merged. First, the cross-repository caller audit is done; its matrix is task 10. Second, the golden-test fixtures are snapshots in this repository under `internal/deployplan/testdata/upstream/` (mctlhq/mctl-api#870, pinned by `provenance.json`). The implementation therefore needs no repository other than mctl-api.

## User stories

- AS an AI session deploying a tenant's repository I WANT to submit a DeployIntent and get back an immutable plan with a diff, a preview host and a digest SO THAT a human or a later grant can approve exactly that effect.
- AS a tenant developer I WANT to plan the same intent twice and get the same digest SO THAT I can tell when nothing has moved.
- AS a tenant member or platform admin I WANT to read a stored plan by id, including whether it has expired, SO THAT I can review it before approving.
- AS a platform operator I WANT production and fresh-repository onboard to be refused with explicit codes SO THAT a plan never describes an effect it does not represent.
- AS a platform security reviewer I WANT `RequiresConfirm: true` to be enforced on every surface that can run the operation SO THAT the registry flag means what it says.

## Acceptance criteria (EARS)

### Plan creation: input and validation

- WHEN an authenticated caller sends `POST /api/v1/deploy/plan` with body `{"intent": <DeployIntent>, "idempotency_key": <optional string>}` THE SYSTEM SHALL validate `intent` against the vendored DeployIntent schema (`deployanalyze.Validate`, pinned by `deployanalyze.SchemaSHA256`) before any other check that reads external state.
- IF the intent fails schema validation (including any unknown field such as `extraObjects`, or any key outside the schema at any depth) THEN THE SYSTEM SHALL answer 422 with code `deploy_intent_invalid` and the schema error, and SHALL NOT drop the field silently.
- IF the request body has a top-level key other than `intent` and `idempotency_key`, is not valid JSON, or is larger than 256 KiB THEN THE SYSTEM SHALL answer 400 with code `deploy_plan_invalid_input`.
- IF `spec.source.revision` is not 40 lowercase hex characters (for example a branch or tag name) THEN THE SYSTEM SHALL answer 422 with code `deploy_revision_not_a_sha` and SHALL NOT resolve the ref.
- IF `spec.environment` is `production` THEN THE SYSTEM SHALL answer 422 with code `prod_requires_promote` and the reason that production is reached only through promote.

### Plan creation: authorization

- WHEN the intent is schema-valid THE SYSTEM SHALL require the caller to hold at least the `MinRole` of the `deploy-service` operation (`operations.RoleDeveloper`, read through `operationMinRole`) on `metadata.tenant`, through `requireTenantRole`, and SHALL otherwise answer 403.
- WHEN the caller is authorized THE SYSTEM SHALL require `spec.source.repository` to be bound to `metadata.tenant`, using the same gitops-annotation binding and portal-binding fallback as `DeployAnalyze`, and SHALL otherwise answer 403 with code `deploy_repository_not_bound`.
- IF the repository binding cannot be read THEN THE SYSTEM SHALL answer 503 with code `deploy_binding_unavailable`.
- IF the service directory exists at `gitops_base_sha` but its `github.com/source-repo` annotation (`gitops.Reader.ComponentSourceRepo`) names a different repository, or names none THEN THE SYSTEM SHALL answer 403 with code `deploy_service_not_bound`. This check runs after the onboard check below, because an absent directory has no annotation. An unreadable annotation SHALL be 503 `deploy_gitops_unavailable`.

### Plan creation: revision check

- WHEN the caller is authorized THE SYSTEM SHALL check that `spec.source.revision` exists in `spec.source.repository` with mctl's GitHub credentials (`deployanalyze.ContentReader.Commit`).
- IF GitHub answers 404 or 422 for the commit THEN THE SYSTEM SHALL answer 422 with code `deploy_revision_unreadable`.
- IF GitHub fails or returns an unusable answer THEN THE SYSTEM SHALL answer 502 with `deploy_github_unavailable` or `deploy_github_malformed`, and SHALL NOT treat the revision as absent.

### Plan creation: compilation

- WHEN the revision exists THE SYSTEM SHALL read `platform-gitops/services/{tenant}/{service}/values.yaml` and the gitops checkout HEAD SHA under one read lock, and SHALL record that SHA as `gitops_base_sha`.
- IF the service directory or its `values.yaml` does not exist at `gitops_base_sha` (a documented absence) THEN THE SYSTEM SHALL answer 422 with code `onboard_requires_preview_onboard` and SHALL NOT produce a plan with `action: onboard`.
- IF the gitops checkout is unsynced or stale, a path element is a symlink or not a plain entry, or the file cannot be read THEN THE SYSTEM SHALL answer 503 with code `deploy_gitops_unavailable`, and SHALL NOT report onboard, refuse as onboard, or return an empty diff.
- IF the base `values.yaml` does not parse as a YAML mapping THEN THE SYSTEM SHALL answer 500 with code `deploy_values_unparseable` and SHALL NOT treat it as "no current values".
- WHEN the base values are read THE SYSTEM SHALL compile the preview overlay with deterministic Go code: apply the intent-derived changes the way `tpl-git-commit` applies them, then the vault-path and store rewrite of `rewrite_preview_values.py`, then the fixed `helm --set` overrides of `wft-preview-deploy`, with the plan's preview id and host.
- IF the preview rewrite refuses the base values (an `externalSecret` mixing `platform/` and `teams/` keys, or a Vault path outside `teams/{tenant}/` and `platform/`) THEN THE SYSTEM SHALL answer 422 with code `deploy_preview_values_refused`, as the workflow script would.
- THE SYSTEM SHALL derive the preview id deterministically from the tenant, service, revision and `gitops_base_sha` (6 characters of `[a-z0-9]`, like the workflow's id), and the host as `{service}-{preview_id}.{PlatformDomain}`.
- THE SYSTEM SHALL compute `values_before_sha256` over the effective preview values that the current base would produce with no intent changes, and `diff` as a unified diff of those values against `values_after`.
- THE SYSTEM SHALL set `action` to `update` for every stored plan in this item.

### Digest

- THE SYSTEM SHALL compute `digest` as `sha256:` plus the hex SHA-256 of a canonical encoding that opens with `mctl-deploy-plan/v1`, followed by length-prefixed fields in this order: tenant, service, environment, canonical intent JSON, revision, `gitops_base_sha`, action, preview id, canonical `values_after`, host.
- THE SYSTEM SHALL NOT include the plan id, timestamps, expiry, idempotency key or the caller in the digest.
- WHEN the same inputs are planned twice THE SYSTEM SHALL produce the same digest, and WHEN any one bound field changes THE SYSTEM SHALL produce a different digest.

### Approval requirement

- WHEN a plan is created THE SYSTEM SHALL set `requires_approval: true` and `required_role: owner` for a preview update, and SHALL name the required approval in the response (`approval: {"required": true, "role": "owner", "reason": "preview_update_requires_approval_until_build_sandbox"}`).
- THE SYSTEM SHALL NOT create, consume or check any grant in this item.

### Storage, read and expiry

- WHEN a plan is created THE SYSTEM SHALL insert exactly one row into `deploy_plans` with an id prefixed `dpl_`, and SHALL write nothing to gitops, Argo or the cluster.
- WHILE a `deploy_plans` row exists THE SYSTEM SHALL offer no UPDATE path for it, and the database SHALL reject any UPDATE with a trigger.
- WHEN a plan is created THE SYSTEM SHALL set `expires_at` to `created_at + 30 minutes` by default. A caller-supplied `ttl_seconds` SHALL be honoured only between 60 and 86400, and anything else SHALL be a 400.
- WHEN a caller sends `GET /api/v1/deploy/plans/{id}` THE SYSTEM SHALL return the stored plan, its digest, and `expired` computed lazily as `now >= expires_at`, and SHALL NOT store `expired`.
- IF the caller is neither a member of the plan's tenant nor a platform admin, or the id does not exist THEN THE SYSTEM SHALL answer 404 with code `deploy_plan_not_found` in both cases.
- IF the plan store is not configured or not reachable THEN THE SYSTEM SHALL answer 503 with code `deploy_plan_store_unavailable`.

### Idempotency

- WHEN a caller repeats a request with the same `(created_by, idempotency_key)` and the computed digest equals the stored one THE SYSTEM SHALL return the stored plan with `replayed: true` and SHALL NOT insert a second row.
- IF the same `(created_by, idempotency_key)` yields a different digest THEN THE SYSTEM SHALL answer 409 with code `deploy_plan_idempotency_conflict`, naming the stored plan id.

### MCP

- THE SYSTEM SHALL expose `mctl_deploy_plan` (input: `intent` as a JSON object, optional `idempotency_key`, optional `ttl_seconds`) and `mctl_get_deploy_plan` (input: `id`) as thin clients of the REST routes, and SHALL bump the tool-count expectation in `internal/mcp/server_test.go`.

### Secrets

- THE SYSTEM SHALL NOT include any secret value, Vault path, token or image-pull credential in any plan response, stored `values_after`, `diff` or audit row. Secret references SHALL appear only as the env name and `property` from `spec.secretRefs`. Every `remoteKey` and `dbSecret.vaultPath` in `values_after` SHALL be replaced with `redacted:sha256:<hex of the real path>`, so the digest still binds the real path.

### Audit

- WHEN a plan is created, read or refused THE SYSTEM SHALL write one audit row with operations `deploy.plan` or `deploy.plan.read`, the caller, the tenant, the service, the digest (when one was computed) and an outcome (`succeeded`, `replayed`, `denied:<code>` or `error:<code>`).

### RequiresConfirm becomes load-bearing

- WHEN `POST /api/v1/operations/{name}/execute` targets an operation with `RequiresConfirm: true` THE SYSTEM SHALL require a top-level body field `"confirm": "yes"` (case-insensitive, trimmed), read before `StripUndeclared`, and SHALL otherwise answer 428 with code `operation_confirmation_required` without submitting a workflow and with a refusal audit row.
- WHEN an MCP tool submits an operation with `RequiresConfirm: true` THE SYSTEM SHALL gate the call on `requireConfirm` before any API call, and SHALL forward `confirm: "yes"` to the execute route. This applies to `mctl_create_tenant` and `mctl_provision_database`, which do not gate today, as well as `mctl_retire_service` and `mctl_delete_tenant`.
- THE SYSTEM SHALL have a parity test that fails when any `RequiresConfirm: true` operation has an MCP tool that reaches the API without confirmation, or is accepted by the generic execute route without confirmation (unless it is `HandlerOnly` and its dedicated handler gates).
- THE SYSTEM SHALL keep `deploy-service` at `RequiresConfirm: false`, and SHALL document in the registry why: the flag is per operation, `action=deploy` is the unattended CI auto-deploy path, and first onboard is gated by plan refusal now and by grants later.

## Out of scope

- Grants, `deploy_apply` and any change to `wft-preview-deploy` so that it accepts the plan's preview id (item `grants` / apply).
- Fresh-repository onboard plans (item `preview-onboard`). Production plans and promote (item `promote-rollback-tools`).
- Image digests and the build of the image for the revision (item `digest`). The plan binds the revision, not a built image.
- Health gate, DeployRecord, rollback, the build sandbox (item `preconditions`).
- Switching mctl-agents `resolve_deploy_target` (mctl-agents#834).
- Replacing `confirm="yes"` with server-held grants (item `grants`).
- Correcting the epic manifest title (done in the PR that binds this issue, in mctlhq/.github).
- Any redesign of #866: the spec is settled. Refreshing or hand-editing `internal/deployplan/testdata/upstream/` (refresh is only through `scripts/refresh-deployplan-upstream.sh`, outside this item). Any change in mctl-gitops or another repository.

## Open questions

- The issue says `environment: prod`. The vendored schema's enum is `preview | production`, so the proposal refuses `production` with `prod_requires_promote`. A literal `prod` already fails the schema (422 `deploy_intent_invalid`).
- Preview id: `wft-preview-deploy` derives the id from the Argo workflow name at apply time. The plan instead fixes a deterministic id. The apply item must pass that id into the template (a new template parameter). Until then the plan's host is what apply will use, not what today's template would pick.
- `image.tag`: today's preview build tag (`GeneratePreviewTag`) uses a timestamp and a uuid, which is not deterministic. The plan records `image.tag` as `rev-<revision>` (the 40-hex SHA). The `digest` and apply items must build and deploy under that tag, or replace it with a digest.
- `required_role: owner` for preview-update approval is this proposal's reading of the epic's risk matrix. The issue names no role.
- `exposure.mode: internal` still compiles the preview ingress, because `wft-preview-deploy` always enables it. Whether an internal intent should get a preview without ingress is left to the apply item.
- The preview TTL (`ttl_hours`, default 24) is a Helm release label, not a value. It is neither bound nor shown in the plan. The apply item may add it.
- External REST callers of the generic execute route for `create-tenant`, `provision-database`, `retire-service` or `delete-tenant` (for example mctl-portal or Backstage) will get 428 until they send `confirm`. Task 10 audits all known callers before merge and is a hard merge gate: every affected caller must already be compatible, or its compatibility change must be merged and released/deployed before (or atomically with) the mctl-api enforcement. An open companion PR is not enough. The caller matrix and rollout order are recorded in the mctl-api PR. Resolved for this retry: the audit is done and recorded in task 10; the only affected external caller, `mctl delete`, sends `confirm` since mctlhq/mctl-gitops#2279 (merged as 7cdfb65).
- An existing `metadata.service` must carry a source-repo annotation naming the intent's repository. A tenant whose repository is bound only in the portal (no service directory yet) can therefore only reach `onboard_requires_preview_onboard`. This is consistent with the owner decision.
- Retry-specific: if the CI step "deploy-plan upstream drift" in `.github/workflows/validate.yml` goes red during implementation because mctl-gitops moved past `provenance.json`'s `source_commit` (7cdfb659), the implementer does not refresh the snapshots in this PR. It reports the drift and builds against the pinned snapshots, which is what the golden tests compare to.
- Retry-specific: `github.com/pmezard/go-difflib` is in `go.sum` but only as an indirect dependency (via testify), not in `go.mod`'s direct requires. The design allows a small in-package LCS line diff instead. This proposal prefers the in-package diff so that `go.mod` gets no new direct dependency. Promoting go-difflib to a direct require is acceptable if the implementer finds the in-package diff unjustifiably large.
- Retry-specific: no acceptance criterion depends on a repository other than mctl-api. If the implementer finds one that does, it records it in the PR and does not reach outside the clone.
