# Design: issue-559-hardening-constrain-every-operation-para

## Current state

- `internal/operations/registry.go`
  - `ParameterDef` (lines 65-84) has `Enum`, `Pattern`, `Secret` and
    `OmitWhenEmpty`. There is no length bound.
  - `Registry.ValidateInput` (lines 234-278) checks, for each declared
    parameter, required-ness, then `Enum`, then `Pattern`. It compiles the
    pattern with `regexp.MustCompile` on every call. An empty value skips all
    checks. A parameter with neither `Enum` nor `Pattern` is never checked.
  - `builtinOperations` (lines 351-897) declares 24 operations. Every one has
    a `WorkflowTemplate`. `smoke-test` declares no parameters. The parameters
    with no `Enum`/`Pattern` today are:
    - deploy-service: dockerfile_repo, git_tag, port, host, env_vars,
      secret_env_vars, health_check_path, dockerfile_path, image_tag,
      min_replicas, max_replicas, cpu_threshold, service_template
    - create-tenant: display_name, description, quota_cpu_req, quota_cpu_lim,
      quota_memory_req, quota_memory_lim, quota_pods, contact_email,
      creator_user_id
    - rollback-service: target_tag
    - preview-deploy: image_tag, ttl_hours
    - add-custom-domain, remove-custom-domain: domain
    - platform-skill-publish: metadata_b64, content_b64, actor
    - platform-skill-deprecate, platform-skill-enable,
      platform-skill-disable: actor
    - mctl-agents-run, mctl-agents-mentor-only, mctl-agents-incidents:
      service (documented "Unused")
    - mctl-agents-implement, mctl-agents-shepherd: slug
    - mctl-agents-approve: approver
- Callers of `ValidateInput`
  - The generic execute handler, `internal/api/handlers_write.go:230`, runs
    `StripUndeclared` (line 103), `ApplyDefaults`, then `ValidateInput`, then
    `Executor.Submit` (line 311).
  - Dedicated handlers: `internal/api/handlers_domains.go:643` and
    `internal/api/handlers_platform_skills.go:193/281/336`.
  - `Executor.Submit` (`internal/operations/executor.go`) does not call
    `ValidateInput`. Its only backstops are the reserved-name checks and
    `splitSecretParams`.
- Server-set values
  - `creator_user_id` is forced to `user.ID` (`handlers_write.go:155`).
  - `approver` is forced to the caller, or relayed by the service principal
    (`handlers_write.go:201-227`).
  - `actor` is `user.ID` (`handlers_platform_skills.go:191/279/335`).
  - `user.ID` can be a GitHub login, a Dex username or display name
    (`internal/auth/oidc.go:148,278,1085`), `ci:<repo>`, `agent:<name>` or
    `surface:<name>`.
- Values existing callers send today
  - `internal/mcp/server.go:619-640` sends `host=none|auto` and
    `env_vars=__CLEAR__`. `operations.ClearSentinel` is in
    `internal/operations/secret_handoff.go:63`.
  - The deploy template treats `image_tag=auto` as "derive the tag".
  - The CI deploy path accepts only `git_tag ~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
    (`internal/api/handlers_ci_deploy.go:58`) and checks `dockerfile_path`
    with `ciRelativePath`.
  - `GeneratePreviewTag` (`internal/operations/preview.go:62`) builds
    `preview-<sanitized<=30>-<unix>-<8 hex>`, which is at most about 60
    characters of `[a-z0-9-]`.
  - `splitSecretParams` already checks `secret_env_vars` keys against
    `envVarName` (`secret_handoff.go:75`). The value never enters the
    Workflow spec.
- Existing tests
  - `internal/operations/registry_test.go` covers patterns for individual
    parameter families (release pin, correlation ids, investigate).
  - `registry_cwft_params_test.go` keeps the declared set in sync with three
    mctl-agents CWFTs.
  - No test asserts that every parameter is constrained.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/` (read through a
  read-only sub-agent):
  - `wft-deploy-service.yaml` pastes several parameters directly into script
    text. Through `tpl-validate-tenant.yaml` and `tpl-git-commit.yaml` these
    are dockerfile_repo, git_tag, host, image_tag, port, env_vars and
    service_template. The template's own checks are:
    - host: `^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(\.[a-z]{2,})+$`
    - image_tag: `^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$`
    - port: `^[0-9]{1,5}$`
    - replicas and cpu_threshold: integers
    - env_vars keys: `^[A-Za-z_][A-Za-z0-9_]*$`
    - service_template: nothing. It is used as a directory name, so `../`
      reaches the directory test.
  - `wft-create-tenant.yaml` passes its parameters through `env:` and
    rejects `"` and newline in display_name and description. It checks
    `creator_user_id` against `[A-Za-z0-9._@-]` and quotas against
    `^[0-9][0-9A-Za-z.]*$`. `contact_email` is not stored.
  - `wft-rollback-service.yaml`, `wft-preview-deploy.yaml`,
    `wft-add-custom-domain.yaml`, `wft-remove-custom-domain.yaml`, the
    `cwft-mctl-agents-*` templates and the `platform-skill-*` templates pass
    parameters through `env:`. target_tag, image_tag and domain are checked
    in-template. `ttl_hours`, `slug` (implement and shepherd) and `service`
    (run) are not checked.
- `$MCTL_GITOPS_ROOT/argo-workflows/service-templates/` contains `default`,
  `worker` and `spring-worker`.
- `$MCTL_GITOPS_ROOT/services/*/*/values.yaml`:
  - Image tags observed: `1.73.0`, `main-9c35416`, `staging-110`,
    `98c8352c1636`, `0.2.27` and similar. All match the OCI tag pattern.
  - Probe paths observed: `/healthz`, `/health`, `/readyz`.
  - Ports observed: 8080, 8787, 80, 5000.
- `$MCTL_GITOPS_ROOT/tenants/*/values.yaml`:
  - CPU values observed: `500m`, `50m`, `100m`, `2`, `3`.
  - Memory values observed: `128Mi`, `256Mi`, `1500Mi`, `2Gi`, `3Gi`,
    `5Gi`, `6Gi`.
  - Pod counts observed: `30`.
- `$MCTL_GITOPS_ROOT/agents-state/*/proposals/`: 851 slugs. Every one
  matches `^[a-z0-9][a-z0-9-]{0,120}$` except 3 that contain dots, e.g.
  `go-chi-v5.3.2-router-upgrade` and `mcp-go-upgrade-v0.50`.
- mctl MCP tools were not called. This change is to code validation only and
  does not depend on runtime configuration. The real values above come from
  gitops.

## Proposed solution

### 1. `ParameterDef.MaxLength`

Add a `MaxLength` field to `ParameterDef`:
`MaxLength int \`json:"maxLength,omitempty"\``.

In `ValidateInput`, check it before `Enum` and `Pattern`:
`if p.MaxLength > 0 && len(val) > p.MaxLength`. On failure, add
`p.Name + ": must be at most N bytes"` to the errors and skip the regex for
that parameter. This bounds regex work on hostile input and never echoes the
value.

The JSON tag is additive. `GET /api/v1/operations` consumers (Backstage, MCP
`mctl_get_operation`) see an extra optional field.

### 2. Shared pattern constants in `registry.go`

Each constant has a comment naming the template check it mirrors. Bounds are
written into the regex where possible, so `MaxLength` is needed only for
multi-line or free-text values.

| Constant | Pattern | Mirrors |
|---|---|---|
| `ociTagPattern` | `^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$` | rollback, preview and tpl-git-commit image_tag check |
| `gitTagPattern` | `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` | `ciGitTagRe`; reuse one definition, see task 2 |
| `githubRepoPattern` | `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` | tpl-git-commit and preview-deploy |
| `repoPathPattern` | `^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$` | preview-deploy dockerfile_path |
| `hostnamePattern` | `^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(\.[a-z]{2,})+$`, MaxLength 253 | add-custom-domain and tpl-git-commit host check |
| `smallIntPattern(n)` | `^[0-9]{1,n}$` | port (5), replicas (3), cpu_threshold (3), ttl_hours (4), quota_pods (4) |
| `cpuQuantityPattern` | `^[0-9]{1,6}(\.[0-9]{1,3})?m?$` | |
| `memoryQuantityPattern` | `^[0-9]{1,9}(\.[0-9]{1,3})?(Ki\|Mi\|Gi\|Ti\|k\|M\|G\|T)?$` | |
| `envBlockPattern` | see below, MaxLength 65536 | |
| `singleLineTextPattern` | `^[^\x00-\x1f\x7f]*$` | |
| `quotedTextPattern` | `^[^\x00-\x1f\x7f"]*$` | create-tenant's `"` and newline rejection |
| `identityPattern` | `^[^\x00-\x1f\x7f]{1,256}$` | |
| `base64Pattern` | `^[A-Za-z0-9+/]*={0,2}$` | |
| `emailPattern` | `^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$`, MaxLength 254 | |

`envBlockPattern` is:

```
^(__CLEAR__|(([A-Za-z_][A-Za-z0-9_]*=[^\x00-\x08\x0a-\x1f\x7f]*)?\n)*([A-Za-z_][A-Za-z0-9_]*=[^\x00-\x08\x0a-\x1f\x7f]*)?)$
```

It accepts newline-separated `KEY=value` lines and blank lines. Values may
contain tab and any printable character, including quotes, `$` and spaces.
It rejects `\r`, NUL and other control characters.

Also add a shared `mctlAgentsServiceEnum`: the existing 15-name list plus
`""`, used by implement, shepherd and reconcile. It replaces those three
literal copies. approve keeps the list without `""`.

### 3. Constraints per parameter

Each value in the table matches what the template needs.

| Operation | Parameter | Constraint |
|---|---|---|
| deploy-service | dockerfile_repo | `githubRepoPattern` |
| | git_tag | `gitTagPattern` |
| | port | `^[0-9]{1,5}$` |
| | host | `^(none\|auto\|<hostname>)$`, MaxLength 253 |
| | env_vars | `envBlockPattern`, MaxLength 65536. Free text (values) |
| | secret_env_vars | exemption: validated by `splitSecretParams`, never enters the spec. MaxLength 65536 |
| | health_check_path | `^/[A-Za-z0-9._~/-]{0,255}$` |
| | dockerfile_path | `repoPathPattern` |
| | image_tag | `ociTagPattern` (accepts `auto`) |
| | min_replicas, max_replicas, cpu_threshold | `^[0-9]{1,3}$` |
| | service_template | `^[a-z0-9][a-z0-9-]{0,62}$` |
| create-tenant | display_name | `quotedTextPattern`, MaxLength 128. Free text |
| | description | `quotedTextPattern`, MaxLength 1024. Free text |
| | quota_cpu_req, quota_cpu_lim | `cpuQuantityPattern` |
| | quota_memory_req, quota_memory_lim | `memoryQuantityPattern` |
| | quota_pods | `^[0-9]{1,4}$` |
| | contact_email | `emailPattern` |
| | creator_user_id | `^[A-Za-z0-9._@-]{1,256}$` (the template's own charset) |
| rollback-service | target_tag | `ociTagPattern` |
| preview-deploy | image_tag | `ociTagPattern` |
| | ttl_hours | `^[0-9]{1,4}$` |
| | git_ref | existing pattern, bounded to `{1,255}` |
| | dockerfile_repo | existing pattern, swapped to the shared bounded constants |
| | dockerfile_path | existing pattern, swapped to the shared bounded constants |
| add-custom-domain, remove-custom-domain | domain | `hostnamePattern`, MaxLength 253. The domains handler already lowercases before validating (`handlers_domains.go:618`) |
| platform-skill-publish | metadata_b64 | `base64Pattern`, MaxLength 16384 |
| | content_b64 | `base64Pattern`, MaxLength 350000 (base64 of the handler's 256 KiB body cap, `handlers_platform_skills.go:232`) |
| platform-skill-* | actor | `identityPattern`, MaxLength 256. Free text (identity) |
| mctl-agents-run, mctl-agents-mentor-only, mctl-agents-incidents | service | `Enum: mctlAgentsServiceEnum`. Includes `""`, so the current "unused" default still passes |
| mctl-agents-implement, mctl-agents-shepherd | slug | `^[a-z0-9][a-z0-9.-]{0,120}$` |
| mctl-agents-approve | slug | widened to the same pattern |
| | approver | `identityPattern`, MaxLength 256. Free text (identity) |

### 4. Free-text list and exemption list

Two maps in `registry.go` (non-test), keyed by operation, then parameter,
with a reason as the value.

`freeTextParameters` lists display_name, description, env_vars, actor and
approver. It documents to mctl-gitops#992 that these must reach a script only
through `env:`, never inline. Each entry must also carry `MaxLength` and a
control-character-excluding anchored `Pattern`. The doc comment points to
mctl-gitops#992.

`unconstrainedParameters` holds only `deploy-service/secret_env_vars`, with
its reason.

The `Description` of each free-text parameter gains the suffix
"Free text; passed to the workflow via env only."

### 5. Registry test

New file `internal/operations/registry_constraints_test.go`.

`constraintViolations(ops []Operation) []string` checks every parameter of
every operation with a non-empty `WorkflowTemplate`. It reports
`"<op>/<param>: ..."` when the parameter is in neither map and has no
constraint. A parameter counts as constrained when `Enum` is non-empty, or
`Pattern` compiles and is anchored: matches `^(\(\?[a-z]+\))?\^` and ends
with `$`. It also reports:
- a free-text entry without `MaxLength`
- a map entry naming an unknown operation or parameter

Tests:
- The real registry passes.
- Proven the other way: for every constrained parameter of the real
  registry, a deep copy with that parameter's `Enum` and `Pattern` cleared
  must yield exactly one violation naming it. This proves removing any
  constraint fails the test.
- A synthetic operation with one bare parameter is reported.
- A fake stale map entry is reported.
- Every `Pattern` compiles, since a bad pattern would otherwise panic at
  request time in `ValidateInput`.

### 6. Real-value compatibility test

A table test, `TestOperationParametersAcceptCurrentRealValues`, runs
`ApplyDefaults` then `ValidateInput` on representative inputs. It uses the
values listed under "Deployed state checked" plus the MCP sentinels, a
`GeneratePreviewTag` output, the CI-shaped deploy input, and every
`ParameterDef.Default`. It expects no errors.

A companion table asserts rejections:
- newline in `git_tag`
- `../x` in `service_template`
- `$(id)` in `host`
- `\r` in `env_vars`
- an over-long `description`
- `"` in `display_name`

## Alternatives

- **Validate in each dedicated handler or in `Executor.Submit` with
  hand-written checks.** Dropped: the checks would be scattered, and a new
  operation would get nothing by default. The registry is the one place every
  submit path already consults and that the test can enumerate.
  `Executor.Submit` could call `ValidateInput` as a backstop. This proposal
  leaves that as a possible follow-up, because handlers already call it and
  Submit has callers that rely on server-built values.
- **Enums for every closed-set field (service_template, quota values).**
  Dropped for service_template: the operation contract is "any template
  directory", so a new template would need an mctl-api release. A strict slug
  pattern removes path traversal without coupling releases. Quotas are
  open-ended numbers.
- **A single generic "safe characters" pattern for every parameter.**
  Dropped: it would either break legitimate free text (env values with `$`,
  `'` and spaces) or be too loose to help structured fields like host and
  tags. Per-field patterns that mirror the template are what the issue asks
  for.
- **Reject undeclared parameters instead of stripping them.** Orthogonal. It
  is already discussed at `handlers_write.go:90-102` and not needed here.

## Platform impact

- **Migrations:** none. There is no storage change.
- **Backward compatibility:**
  - The `maxLength` JSON field is additive.
  - Validation is stricter by design. Every value observed in deployed
    gitops state, plus every sentinel and generated value in the code, is
    covered by the compatibility test.
  - Residual risk: a tenant using a git tag with `/`, a probe path with a
    query string, CRLF line endings in `env_vars`, or a Dex display-name
    identity with characters outside `[A-Za-z0-9._@-]` on create-tenant.
    The last one already fails today inside `wft-create-tenant.yaml`, so
    there is no change except an earlier and clearer 400. These cases are in
    Open questions.
- **Resource impact:** negligible. The length check runs before the regex.
  Regex compilation per call is unchanged; caching compiled patterns is an
  optional follow-up.
- **Risks and mitigations:**
  - A legitimate caller is rejected. Mitigation: a clear 400 naming the
    parameter and pattern, the compatibility test, and a one-commit revert.
  - Drift between API patterns and template checks. Mitigation: a comment on
    each constant naming the template line it mirrors. mctl-gitops#992
    remains the primary fix.
