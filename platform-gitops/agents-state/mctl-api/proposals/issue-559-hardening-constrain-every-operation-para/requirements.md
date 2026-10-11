# Constrain every operation parameter that reaches a workflow template

## Context

`internal/operations/registry.go` declares the parameters of every
workflow-backed operation (`builtinOperations`). `Registry.ValidateInput`
enforces only the `Enum` and `Pattern` that a `ParameterDef` declares, so a
parameter that declares neither is forwarded to the Argo
ClusterWorkflowTemplate exactly as the caller sent it. Today that includes,
among others, `deploy-service` `dockerfile_repo`, `git_tag`, `port`, `host`,
`env_vars`, `health_check_path`, `dockerfile_path`, `image_tag`,
`min_replicas`, `max_replicas`, `cpu_threshold`, `service_template`;
`create-tenant` `display_name`, `description`, the five `quota_*` values,
`contact_email`, `creator_user_id`; `rollback-service` `target_tag`;
`preview-deploy` `image_tag`, `ttl_hours`; `add-custom-domain` /
`remove-custom-domain` `domain`; the platform-skill `metadata_b64`,
`content_b64`, `actor`; the mctl-agents `service` (run modes), `slug`
(implement, shepherd) and `approver` (approve).

Several of these are still pasted into inline script text in mctl-gitops
(e.g. `wft-deploy-service.yaml` via `tpl-validate-tenant.yaml` and
`tpl-git-commit.yaml`: `git_tag`, `host`, `env_vars`, `service_template`,
`image_tag`, `dockerfile_repo`). mctlhq/mctl-gitops#992 fixes the gitops side;
this issue (mctlhq/mctl-api#559) is the API-side defence in depth: every
parameter gets an explicit, template-matching constraint, a registry test
makes an unconstrained parameter a build failure, and the few genuinely
free-text fields are listed and documented so the gitops side knows to pass
them through `env:` only.

## User stories

- AS a platform operator I WANT every operation parameter validated against
  the shape its workflow template actually needs SO THAT a malformed or
  hostile value is refused with a 400 before any Workflow is submitted.
- AS a developer adding a new operation or parameter I WANT a failing unit
  test when I forget to constrain it SO THAT the gap cannot silently reopen.
- AS a gitops template author I WANT a single authoritative list of the
  parameters that stay free text SO THAT I know which ones must only ever
  reach a script through `env:`.
- AS an existing caller (MCP tools, Backstage, CI deploy job, mctl-agents
  DevLoop) I WANT my current real values to keep validating SO THAT the
  hardening does not break deployments.

## Acceptance criteria (EARS)

- WHEN an operation in `builtinOperations` has a non-empty `WorkflowTemplate`
  THE SYSTEM SHALL declare, for each of its parameters, either a non-empty
  `Enum` or an anchored `Pattern` (starting with `^`, optionally after an
  inline flag group such as `(?s)`, and ending with `$`).
- WHEN a parameter is declared free text (listed in the registry's
  free-text set) THE SYSTEM SHALL still declare a `MaxLength` greater than
  zero and a `Pattern` that excludes ASCII control characters other than
  those the field legitimately needs (newline for multi-line fields).
- WHEN a caller submits a value longer than a parameter's `MaxLength`
  THE SYSTEM SHALL return a validation error naming the parameter and the
  limit, without echoing the value.
- WHEN a caller submits a value that fails a parameter's `Enum` or
  `Pattern` THE SYSTEM SHALL return HTTP 400 with `validation failed: ...`
  from `POST /api/v1/operations/{name}/execute` and SHALL NOT call
  `Executor.Submit`.
- WHEN `go test ./internal/operations/...` runs THE SYSTEM SHALL fail if any
  parameter of a workflow-backed operation has no constraint and is not in
  the documented exemption list, naming the operation and parameter.
- WHEN the exemption / free-text list names an operation or parameter that
  does not exist in the registry THE SYSTEM SHALL fail the same test (no
  stale entries).
- WHEN the registry test's checker is given a synthetic operation with one
  unconstrained parameter THE SYSTEM SHALL report exactly that parameter
  (the test is proven to fail, not only to pass).
- WHILE a current real value is used by an existing caller (MCP
  `mctl_deploy_service` sentinels `host=none|auto`, `env_vars=__CLEAR__`,
  `image_tag=auto`; CI deploy `git_tag`; preview auto-generated
  `image_tag`; dotted proposal slugs such as `mcp-go-upgrade-v0.50`;
  service templates `default`, `worker`, `spring-worker`; deployed quota
  values such as `500m`, `1500Mi`, `5Gi`) THE SYSTEM SHALL accept it.
- IF a parameter is `Secret` (`secret_env_vars`) THEN THE SYSTEM SHALL
  continue to validate it in `splitSecretParams` and SHALL list it in the
  exemption list with that reason, plus a `MaxLength`.
- IF a parameter's value is supplied server-side (`creator_user_id`,
  `actor`, `approver`) THEN THE SYSTEM SHALL still constrain it, so that a
  malformed authenticated identity is refused rather than forwarded.

## Out of scope

- Changing any ClusterWorkflowTemplate in mctl-gitops (mctlhq/mctl-gitops#992
  owns moving parameters from inline script text to `env:`).
- Changing MCP tool input schemas in `internal/mcp/server.go` (they keep
  forwarding to the REST path, which now validates).
- Rejecting undeclared parameters instead of stripping them
  (`StripUndeclared` behaviour is unchanged).
- Handler-built parameters that never pass through the registry's
  declared set (e.g. values built server-side and not declared).
- Semantic checks beyond shape (e.g. that `min_replicas <= max_replicas`,
  that a domain resolves, that a tag exists in GHCR).

## Open questions

- `git_tag`: the CI deploy path already restricts it to
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` (`internal/api/handlers_ci_deploy.go`
  `ciGitTagRe`). This proposal applies the same pattern to all callers, which
  rejects git tags containing `/` (e.g. `release/1.0`). The deploy template
  derives the image tag from `git_tag` by stripping a leading `v`, and an OCI
  tag cannot contain `/`, so such a tag cannot deploy today anyway. The
  reviewer should confirm.
- `health_check_path`: proposed as `^/[A-Za-z0-9._~/-]{0,255}$`, which
  rejects query strings. No deployed service uses one (deployed probe paths
  observed: `/healthz`, `/health`, `/readyz`), but a tenant could.
- `mctl-agents-approve` `slug` currently uses `^[a-z0-9][a-z0-9-]{0,120}$`
  while 3 existing proposal directories contain dots (e.g.
  `go-chi-v5.3.2-router-upgrade`). This proposal uses
  `^[a-z0-9][a-z0-9.-]{0,120}$` for implement/shepherd `slug` and widens
  approve's to match. The reviewer should decide whether approve stays
  narrower on purpose.
- The `quota_*` patterns are tighter than the template's own check
  (`^[0-9][0-9A-Za-z.]*$`). They accept every deployed tenant quota value
  observed, but a previously valid admin input such as `2e3` would now be
  rejected.
