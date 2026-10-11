# Tasks: issue-559-hardening-constrain-every-operation-para

- [ ] 1. Add `MaxLength int \`json:"maxLength,omitempty"\`` to `ParameterDef`
  in `internal/operations/registry.go`, and enforce it in
  `Registry.ValidateInput` before the `Enum` and `Pattern` checks. A failing
  length check skips the regex for that parameter and produces the error
  `"<name>: must be at most N bytes"`. — DoD:
  - A value over the limit is rejected without echoing the value.
  - Existing tests still pass.
- [ ] 2. Add the shared pattern constants to `registry.go`: `ociTagPattern`,
  `gitTagPattern`, `githubRepoPattern`, `repoPathPattern`, `hostnamePattern`,
  `envBlockPattern`, `singleLineTextPattern`, `quotedTextPattern`,
  `identityPattern`, `base64Pattern`, `emailPattern`, `cpuQuantityPattern`
  and `memoryQuantityPattern`, plus `mctlAgentsServiceEnum`. Each constant
  carries a comment naming the gitops template check it mirrors. Make
  `ciGitTagRe` in `internal/api/handlers_ci_deploy.go` compile from
  `operations.GitTagPattern` (export it), so the two cannot drift. — DoD:
  - The constants compile.
  - The CI deploy tests still pass, unchanged.
- [ ] 3. (depends on 1, 2) Apply a constraint to every parameter listed in
  design.md section 3. This covers deploy-service, create-tenant,
  rollback-service, preview-deploy, add-custom-domain, remove-custom-domain,
  the platform-skill-* operations, the mctl-agents run/mentor-only/incidents
  `service`, the implement/shepherd/approve `slug`, and `approver`. Replace
  the duplicated service enum literals in implement, shepherd and reconcile
  with `mctlAgentsServiceEnum`. — DoD:
  - Every parameter of every operation with a `WorkflowTemplate` has an
    `Enum` or an anchored `Pattern`, except `deploy-service/secret_env_vars`.
- [ ] 4. (depends on 3) Add `freeTextParameters` and `unconstrainedParameters`
  to `registry.go`: maps of operation, then parameter, then reason, with a
  doc comment pointing to mctlhq/mctl-gitops#992.
  - `freeTextParameters` lists create-tenant display_name and description,
    deploy-service env_vars, the platform-skill-* actor, and
    mctl-agents-approve approver.
  - `unconstrainedParameters` lists only deploy-service secret_env_vars,
    with its reason: validated by `splitSecretParams` and never enters the
    Workflow spec.
  - Each free-text parameter's `Description` gets the suffix
    "Free text; passed to the workflow via env only."
  - Every free-text parameter, and `secret_env_vars`, carries a `MaxLength`.

  DoD:
  - The maps exist with reasons.
  - Descriptions are updated.
- [ ] 5. (depends on 4) Add `internal/operations/registry_constraints_test.go`
  with `constraintViolations(ops []Operation) []string` and tests T1-T5. —
  DoD:
  - `go test ./internal/operations/...` passes.
  - Clearing any one constraint in a copy of the registry makes the checker
    report it.
- [ ] 6. (depends on 3) Add the real-value compatibility and rejection
  tables (T6, T7), and update any existing test that relied on an
  unconstrained value. Check `internal/api` handler tests and `e2e/` fixtures
  for values such as `host`, `git_tag`, `quota_*` and `slug`, and make each
  fixture match the new pattern rather than loosening it. — DoD:
  - `go test ./...` passes.
  - `go vet` and `golangci-lint` are clean.
- [ ] 7. Note in the PR description, for mctlhq/mctl-gitops#992, the
  parameters that remain free text and the gitops template lines each
  pattern mirrors. — DoD:
  - The PR body lists `freeTextParameters` and links mctl-gitops#992.

## Tests

- [ ] T1. `TestEveryWorkflowParameterIsConstrained`:
  `constraintViolations(builtinOperations)` is empty.
- [ ] T2. `TestConstraintCheckFailsWhenAnyConstraintIsRemoved`: for each
  parameter of each operation in the real registry that is not in
  `unconstrainedParameters`, deep-copy the registry and clear that
  parameter's `Enum` and `Pattern`. The checker must report exactly
  `"<op>/<param>"`. This proves the test fails both ways.
- [ ] T3. `TestConstraintCheckReportsSyntheticBareParameter` and
  `TestConstraintCheckReportsUnanchoredPattern`. The second uses a pattern
  such as `[a-z]+` with no `^`/`$`.
- [ ] T4. `TestFreeTextAndExemptionListsHaveNoStaleEntries`. Every map
  entry names an existing operation and parameter, and every free-text entry
  has `MaxLength > 0`.
- [ ] T5. `TestEveryParameterPatternCompiles`.
- [ ] T6. `TestOperationParametersAcceptCurrentRealValues`. Each input goes
  through `ApplyDefaults` then `ValidateInput`, and must produce no errors.
  Inputs:
  - MCP sentinels: `host=none`, `host=auto`, `env_vars=__CLEAR__`,
    `image_tag=auto`
  - a CI deploy input: `git_tag=1.73.0`, `dockerfile_repo=mctlhq/mctl-api`
  - a `GeneratePreviewTag("feat/my-feature")` output
  - deployed image tags: `main-9c35416`, `staging-110`, `98c8352c1636`
  - quotas: `500m`, `50m`, `2`, `1500Mi`, `5Gi`, `30`
  - probe paths: `/healthz`, `/readyz`
  - service templates: `default`, `worker`, `spring-worker`
  - slugs: `go-chi-v5.3.2-router-upgrade`,
    `issue-559-hardening-constrain-every-operation-para`
  - an env block with `$`, quotes, spaces and blank lines
  - identities: `octocat`, `dev-user`, `agent:implementer`
  - every `ParameterDef.Default`
- [ ] T7. `TestOperationParametersRejectInjectionShapes`. Each of these must
  produce a validation error:
  - newline in `git_tag`, `image_tag` or `target_tag`
  - `../x` in `service_template`
  - `a.com;id` or `$(id)` in `host` or `domain`
  - `\r` or NUL in `env_vars`
  - `"` in `display_name`
  - `description` longer than 1024 bytes
  - non-numeric `port`, `ttl_hours` or `min_replicas`
  - a non-base64 `content_b64`
- [ ] T8. A handler-level test in `internal/api` for the generic execute
  path: an invalid `deploy-service` `host` returns 400
  `validation failed: host: ...` and the fake executor records no submit.

## Rollback

The change is in code only. There is no storage, API-shape removal or gitops
change. To roll back, revert the PR and redeploy mctl-api with the previous
image tag (`mctl_rollback_service` for mctl-api). If only one pattern turns
out to reject a legitimate caller, a targeted follow-up can widen that one
pattern while leaving the registry test in place. Any widening must keep the
test green rather than removing the constraint.
