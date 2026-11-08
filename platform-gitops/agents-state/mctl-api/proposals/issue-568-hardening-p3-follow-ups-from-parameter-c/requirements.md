# Hardening: P3 follow-ups from parameter constraints (#561)

## Context

mctl-api#561 (for #559) gave every workflow-bound operation parameter in
`internal/operations/registry.go` an Enum or an anchored Pattern, plus a
`MaxLength`. The review rounds on #561 left nine non-blocking P3 findings.
mctl-api#568 collects them. Most are places where the MCP layer
(`internal/mcp/server.go`) sends values the registry now rejects, or where two
copies of one rule have drifted apart (the CI deploy path and the registry,
`internal/api` and `internal/operations`). The rest are a weak spot in the
constraint test and loose or misleading patterns and comments.

These issues are small, but each causes an avoidable 400 for a valid caller,
weakens a guarantee the drift tests are supposed to give, or leaves comments
that do not match the code. One item, the `MaxLength int32` rationale, has
already been done: `ParameterDef.MaxLength` in `registry.go` already carries
the 120-byte / `rangeValCopy` comment. That item is only verified here, not
re-implemented.

## User stories

- AS an MCP client calling `mctl_deploy_service` I WANT a host written as `API.Example.com.` to be accepted as `api.example.com` SO THAT I do not get a pattern error for a host the platform would treat as the same.
- AS an MCP client calling `mctl_remove_custom_domain` / `mctl_verify_domain` I WANT `team`/`service` to be trimmed and lowercased SO THAT the domain workflows do not reject `Labs` while the REST path accepts it.
- AS a self-service user signing in through ZITADEL I WANT create-tenant either to accept my identity or to tell me clearly why it does not SO THAT I do not hit an unexplained pattern error on a field I never sent.
- AS a platform maintainer I WANT the constraint test, the shared patterns and the comments to say what the code does SO THAT later drift is caught by tests and not found in review.

## Acceptance criteria (EARS)

1. WHEN `mctl_deploy_service` receives a non-empty `host` THE SYSTEM SHALL pass `normalizeDomain(host)` (trimmed, lowercased, root dot stripped) to `/api/v1/operations/deploy-service/execute`.
2. WHEN `mctl_deploy_service` receives no `host` THE SYSTEM SHALL keep sending `none` for `worker-service` and `auto` otherwise, unchanged.
3. WHEN `mctl_remove_custom_domain` or `mctl_verify_domain` builds the domain-list query, the delete call or the workflow `wfParams`, THE SYSTEM SHALL use the `team` and `service` values after trim and lowercase. This is the same transformation as `normalizeIdentifier` in `internal/api/handlers_domains.go`.
4. WHILE `creator_user_id` is set by the server from `user.ID` THE SYSTEM SHALL keep the `^[A-Za-z0-9._@-]{1,256}$` pattern. That pattern mirrors the guard in `wft-create-tenant.yaml`, which splices the value into YAML unquoted. The parameter description SHALL say "authenticated user ID set by the server", not "GitHub user ID".
5. IF the session's `user.ID` does not match the `creator_user_id` pattern on create-tenant THEN THE SYSTEM SHALL refuse before `ValidateInput` with a 400 that names the identity format as the cause, and SHALL write a `denied` audit entry. The message SHALL NOT tell the caller to change a parameter they never sent.
6. THE SYSTEM SHALL bound `mctl-agents-investigate`'s `human_input_responses` with a `MaxLength`.
7. WHILE `TestEveryWorkflowParameterIsConstrained` runs THE SYSTEM SHALL count a Pattern-only parameter as constrained only if it has `MaxLength > 0` or its parsed Pattern (`regexp/syntax`) contains no unbounded repetition (`*`, `+`, `{n,}`). An Enum still counts on its own.
8. THE SYSTEM SHALL use one shared repository-relative-path rule for the registry's `dockerfile_path` (`repoPathPattern`) and the CI deploy path (`ciDockerfilePathRe` / `ciRelativePath`). Under that rule, segments with a leading dot (for example `.docker/Dockerfile`) are accepted, while the segments `.` and `..`, empty segments, absolute paths and a leading `-` are refused.
9. THE SYSTEM SHALL have a test proving that `operations.hostnameLabel` and `internal/api`'s `hostnameLabelPattern` accept and reject the same labels, and that the source strings are byte-identical.
10. THE SYSTEM SHALL correct the comment on `serviceEnumOperationToTool` in `internal/mcp/server_test.go`. The registry's `mctl-agents-incidents` `service` parameter does carry an Enum. The operation is excluded only because `mctl_trigger_incident_responder` exposes no `service` argument.
11. IF `preview-deploy`'s `git_ref` starts with `-`, contains `..` or `//`, has a segment starting with `.`, ends in `/`, `.` or `.lock`, or is longer than 255 bytes, THEN THE SYSTEM SHALL refuse it in `Registry.ValidateInput`. Branch names, tags and 40-hex SHAs that pass `git check-ref-format --allow-onelevel` with the current charset SHALL keep passing.
12. WHILE every change above is applied THE SYSTEM SHALL keep `TestConstraintCheckFailsWhenAnyConstraintIsRemoved`, `TestServiceEnumsMatchRegistry` and the MCP tool-count expectation in `server_test.go` passing. This proposal adds and removes no tools.

## Out of scope

- Changing `wft-create-tenant.yaml` in mctl-gitops (for example, quoting `userId` or widening its charset to `+`). That template is a separate repository; this proposal only makes mctl-api's refusal explicit.
- Normalizing `host` on the REST `POST /api/v1/operations/deploy-service/execute` path for non-MCP callers.
- Adding new MCP tools or parameters, or changing `mctl_trigger_incident_responder`'s schema.
- Re-implementing the `MaxLength int32` comment, which already exists at `registry.go:74-76`.
- Full `git check-ref-format` semantics outside the current charset (for example `@{`, `~`, `^`, `:`), which the charset already excludes.

## Open questions

- Which ZITADEL identity shapes actually reach `user.ID`? The deployed `MCTL_OIDC_PROVIDERS` (zitadel-iac `mctl-api.tf`) sets no `display_claims`, so `provider_oidc.go` falls back to `preferred_username`, then `email`, then `sub`. A login name or email containing `+` (or other characters ZITADEL allows) falls outside `[A-Za-z0-9._@-]`. This proposal keeps the pattern and makes the refusal explicit (criterion 5). Widening the pattern needs a matching mctl-gitops change to `wft-create-tenant.yaml`, which should be filed separately if real users are affected.
- What should the `MaxLength` for `human_input_responses` be? The proposal uses 65536 bytes, the same as `env_vars`. The real ceiling depends on how many answers mctl-agents' DevLoop can carry; the mctl-agents maintainers should confirm it.
- Is accepting leading-dot directories (the CI rule) better than rejecting them (the registry rule)? The proposal accepts them, because `.docker/` and `.devcontainer/` Dockerfiles are common and `.`/`..` segments stay refused.
