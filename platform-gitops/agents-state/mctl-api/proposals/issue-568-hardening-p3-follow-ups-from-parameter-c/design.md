# Design: issue-568-hardening-p3-follow-ups-from-parameter-c

## Current state

Every item below was checked in the clone. Line numbers are from the current
clone; several have drifted from the ones quoted in the issue.

1. **`deploy-service` host from MCP.** `toolDeployService`'s handler
   (`internal/mcp/server.go:805-818`) runs `extractStringParams` and fills in
   `host` = `none`/`auto` only when the key is missing. A caller-supplied
   `host` is forwarded verbatim. The registry's `host` parameter
   (`internal/operations/registry.go:453`) is
   `^(none|auto|` + hostnameCore + `)$`, which is lowercase-only with no root
   dot. The `normalizeDomain` doc comment (`server.go:1761-1764`) claims
   "every hostname this package submits to a domain workflow goes through
   it", but deploy-service's host does not.
2. **`team`/`service` in the domain tools.** `toolRemoveCustomDomain`
   (`server.go:1659`) reads `team`/`service` as raw strings (`args["team"]`),
   and so does `toolVerifyDomain` (`server.go:1769`). They are used in the list
   query, the delete call and the `wfParams` maps (`server.go:1743-1747`,
   `1848-1852`). Only `domain` is normalized. The REST side normalizes with
   `normalizeIdentifier` (`internal/api/handlers_domains.go:128`, trim plus
   lowercase), and the registry's `team_name`/`service_name` are
   lowercase-only. `internal/mcp/commerce.go:normalizeTenantArg` already
   applies the same trim-and-lowercase in the mcp package.
3. **`creator_user_id`.** `internal/api/handlers_write.go:219-220` sets
   `input["creator_user_id"] = user.ID` before validation. The registry
   (`registry.go:503`) declares the description "GitHub user ID of the
   workspace creator" and the pattern `^[A-Za-z0-9._@-]{1,256}$`. `user.ID` is
   not always a GitHub login. For a generic OIDC provider (ZITADEL),
   `userFromVerified` (`internal/auth/oidc.go:1378-1384`) sets
   `ID = Identity.Display`, and `provider_oidc.go:114-115` defaults
   `DisplayClaims` to `preferred_username`, `email`, `sub`. An email or login
   name containing `+` falls outside the charset. The template enforces the
   same charset: `wft-create-tenant.yaml:785-799` in mctl-gitops splices the
   value unquoted into `- userId: <value>`, so the pattern is a real
   YAML-injection boundary, not just decoration.
4. **`human_input_responses`.** `registry.go:920-922` declares Pattern
   `(?s)^\[.*\]$` with no `MaxLength`. `isConstrained`
   (`internal/operations/registry_constraints_test.go:11-16`) only checks for
   an anchored `^...$`, so the parameter passes
   `TestEveryWorkflowParameterIsConstrained` while bounding nothing.
5. **Dotfile directories.** `ciDockerfilePathRe`
   (`internal/api/handlers_ci_deploy.go:61`) is
   `^[A-Za-z0-9._][A-Za-z0-9._/-]{0,199}$`, and `ciRelativePath` (`:177`)
   additionally refuses empty, `.` and `..` segments. That rule accepts
   `.docker/Dockerfile` (and also `a/-b`). `repoPathPattern`
   (`registry.go:376`) requires every segment to start with `[A-Za-z0-9_]`, so
   it refuses `.docker/Dockerfile`, even though its comment says it is
   "matching ciRelativePath". A CI deploy with such a path passes the CI gate
   and then fails `ValidateInput`.
6. **Stale comment.** `internal/mcp/server_test.go:974-978` says
   `mctl-agents-incidents` "has no Enum at all". `registry.go:801` gives it
   `Enum: mctlAgentsServiceEnum`. The operation is in fact excluded because
   `mctl_trigger_incident_responder` has no `service` argument.
7. **`hostnameLabel`.** `registry.go:382` `hostnameLabel` and
   `handlers_domains.go:134` `hostnameLabelPattern` are two hand-copied
   strings, and nothing pins them together. `internal/api` already imports
   `operations` for a shared pattern (`ciGitTagRe =
   regexp.MustCompile(operations.GitTagPattern)`, `handlers_ci_deploy.go:58`).
8. **`MaxLength int32`.** This is already done. `registry.go:74-76` reads
   "int32 rather than int keeps ParameterDef at 120 bytes, below gocritic's
   rangeValCopy threshold". No code change is needed; the item is verified
   only.
9. **`git_ref`.** `preview-deploy` `git_ref` (`registry.go:591`) is
   `^[A-Za-z0-9._/-]{1,255}$`, with no `MaxLength`. It accepts `-x`, `a/../b`,
   `a//b`, `a/` and `x.lock`. It feeds `GeneratePreviewTag`
   (`internal/operations/preview.go:62`) and the build workflow.
   `Registry.ValidateInput` (`registry.go:238-275`) already has op-specific
   checks after the per-parameter loop (the create-tenant reserved-name
   check).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/wft-create-tenant.yaml`
  (lines 785-799): the template refuses `creator_user_id` outside
  `[A-Za-z0-9._@-]` and splices it unquoted into YAML. This confirms that
  dropping the registry pattern would only move the failure into the
  workflow.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`
  (lines 424-433): mctl-api reads `MCTL_OIDC_PROVIDERS` from Secret
  `mctl-api-oidc-zitadel`, and Dex is gone.
- `$MCTL_GITOPS_ROOT/helm-charts/zitadel-iac/iac/mctl-api.tf` (lines
  225-232): the single provider `zitadel` (issuer `https://auth.mctl.ai`) sets
  no `display_claims`, so the default chain `preferred_username`, `email`,
  `sub` applies.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/wft-preview-deploy.yaml`
  and `wft-deploy-service.yaml`: grep found no separate shape check on
  `git_ref` or `dockerfile_path`, so the registry is the only gate.
- The real ZITADEL user login names were not observed. No read-only tool here
  exposes them, and that gap is recorded under Open questions. mctl MCP tools
  were not needed; mctl-api's own service values are not under
  `services/<tenant>/` in this checkout.

## Proposed solution

Each item is a small, independent change. All of them can ship in one PR.

1. **Host normalization (`internal/mcp/server.go`).** In `toolDeployService`'s
   handler, after the `none`/`auto` default block, add
   `if h := params["host"]; h != "" { params["host"] = normalizeDomain(h) }`.
   `AUTO` becomes `auto`, which is still valid. Update the `normalizeDomain`
   doc comment to say "every hostname this package submits to a workflow
   (domain workflows and deploy-service host)".
2. **Identifier normalization (`internal/mcp`).** Add
   `func normalizeIdentifier(s string) string { return strings.ToLower(strings.TrimSpace(s)) }`
   to `internal/mcp/server.go`, with a comment that it mirrors
   `internal/api.normalizeIdentifier`. `normalizeTenantArg` may reuse it. In
   `toolRemoveCustomDomain` and `toolVerifyDomain`, normalize `team` and
   `service` right after they are read, so the list query, the delete call and
   both `wfParams` maps all use the same value. The REST side already
   normalizes, so this changes nothing for lowercase callers.
3. **`creator_user_id` (`registry.go`, `handlers_write.go`).** Keep the
   pattern, because it is the same guard the template applies and the template
   inserts the value unquoted.
   - Rename the description to "Authenticated user ID of the workspace
     creator (set by the server from the session; never caller-supplied)".
   - Add a comment explaining why the pattern stays and that it must match
     `wft-create-tenant.yaml`.
   - Expose the pattern as an exported const, `CreatorUserIDPattern`.
   - In `handlers_write.go`, where `creator_user_id` is forced, check `user.ID`
     against that compiled pattern. On a mismatch, write a `denied` audit entry
     and return `400` "your sign-in identity %q cannot be recorded as a
     workspace owner (allowed characters: A-Z a-z 0-9 . _ @ -)".
   - Replace the comment "prevent spoofing" with one that says the value is
     forced from the session and pre-checked.
4. **`human_input_responses` bound plus a stricter heuristic.**
   - Add `MaxLength: 65536` to the parameter.
   - In `registry_constraints_test.go`, change `isConstrained` so that a
     Pattern-only parameter (no Enum) needs either `MaxLength > 0` or a pattern
     that, parsed with `regexp/syntax.Parse(p.Pattern, syntax.Perl)` and
     simplified, contains no `OpStar`, `OpPlus` or `OpRepeat` with `Max == -1`.
     Anchoring stays required.
   - Audit the existing registry: any Pattern-only parameter that is unbounded
     and has no `MaxLength` gets an explicit `MaxLength` (for example
     `git_ref`, see item 9), so the test stays green.
   - Extend `TestConstraintCheckReportsSyntheticAndUnanchored` with an
     anchored-but-unbounded case such as `(?s)^\[.*\]$` with no `MaxLength`.
5. **One repo-path rule.**
   - In `registry.go`, replace `repoPathPattern` with an exported
     `RepoPathPattern =
     ^\.?[A-Za-z0-9_][A-Za-z0-9._-]*(/\.?[A-Za-z0-9_][A-Za-z0-9._-]*)*$`, plus
     `RepoPathMaxLength = 256`. A segment may begin with one dot followed by an
     alphanumeric or `_`, so `.docker` and `.devcontainer` are accepted. `.`,
     `..`, `..x`, empty segments, absolute paths and a leading `-` are still
     refused by construction.
   - Use `RepoPathMaxLength` for both `dockerfile_path` parameters.
   - In `handlers_ci_deploy.go`, set
     `ciDockerfilePathRe = regexp.MustCompile(operations.RepoPathPattern)` and
     make `ciRelativePath` check `len(p) <= operations.RepoPathMaxLength`
     first. Keep the explicit segment loop as defense in depth.
   - Fix both comments so they name the shared const.
6. **Comment fix (`internal/mcp/server_test.go`).** Reword the comment to say
   that `mctl-agents-incidents` is excluded because
   `mctl_trigger_incident_responder` exposes no `service` argument (its
   registry Enum is not mirrored anywhere). Fix the matching sentence in the
   `TestServiceEnumsMatchRegistry` doc comment if it repeats the claim.
7. **Shared hostname label.**
   - Export `operations.HostnameLabelPattern` (the current `hostnameLabel`)
     and keep `hostnameLabel` as an alias, or replace it.
   - In `handlers_domains.go`, define
     `hostnameLabelPattern = regexp.MustCompile("^" + operations.HostnameLabelPattern + "$")`.
   - Add a test in `internal/api` asserting
     `hostnameLabelPattern.String() == "^"+operations.HostnameLabelPattern+"$"`
     and checking a few labels on both sides (`xn--p1ai`, `a`, `-a`, `a-`, a
     64-character label, `A`). This pins the two forever, because there is now
     only one source.
8. **`MaxLength int32` comment.** No change; verified present.
9. **Git refs.**
   - Add `gitRefPattern = ^[A-Za-z0-9_](\.?[A-Za-z0-9_-])*(/[A-Za-z0-9_](\.?[A-Za-z0-9_-])*)*$`.
     Each segment starts with an alphanumeric or `_`, never has two dots in a
     row and never ends in a dot, and segments are joined by single slashes.
     That rules out a leading `-`, `..`, `//`, a trailing `/`, a trailing `.`
     and a leading `.` in any segment.
   - Set `MaxLength: 255` on `git_ref`.
   - RE2 cannot express "does not end in `.lock`", so add an op-specific check
     in `Registry.ValidateInput`, next to the create-tenant block: for
     `preview-deploy`, any `/`-segment of `git_ref` ending in `.lock` adds
     `git_ref: must not have a component ending in .lock`.
   - 40-hex SHAs, `feat/foo-bar`, `v1.2.3` and `release/2026.11` all still
     match.

## Alternatives

- **Drop the `creator_user_id` pattern instead of pre-checking.** Rejected.
  `wft-create-tenant.yaml` enforces the same charset and splices the value
  unquoted, so the request would fail later inside the workflow, and the
  registry would lose its mirror of a real injection guard. Widening both
  sides (for example adding `+`) is the real fix for affected identities, but
  it needs a coordinated mctl-gitops change and is left as an open question.
- **Pin `hostnameLabel` only with an equality test, keeping two literals.**
  This works, but the test cannot read an unexported `operations` const from
  `internal/api`. It would have to hard-code the string a third time or
  export it anyway. Exporting and deriving matches the `GitTagPattern`
  precedent and removes the duplication.
- **Make the repo-path rule refuse dotfile directories on both sides.**
  Rejected. `.docker/` and `.devcontainer/` Dockerfiles are common, CI callers
  may already rely on them passing the CI gate, and `.`/`..` safety does not
  depend on refusing a leading dot.
- **Add a per-parameter validator func to `ParameterDef` for `.lock`.**
  Rejected. It grows the struct past the 128-byte `rangeValCopy` threshold
  that `MaxLength int32` was chosen to avoid, for one parameter. An
  op-specific check in `ValidateInput` already has precedent.
- **Heuristic "Pattern must end in `}$`".** Rejected in favor of parsing with
  `regexp/syntax`. Many bounded patterns end in `?$` or `)$` (for example
  `cpuQuantityPattern`), and the suffix heuristic would misjudge them.

## Platform impact

- **Migrations.** None. Nothing is stored and no schema changes.
- **Backward compatibility.**
  - Item 1 and item 2 only accept more inputs: mixed-case or dotted values that
    used to get a 400 now succeed.
  - Item 5 starts accepting `.docker/...` on the registry side. It also
    slightly tightens the CI side: a segment starting with `-` (`a/-b`) is now
    refused. Its maximum length grows from 200 to 256 bytes.
  - Item 9 refuses `git_ref` values that git itself would refuse as ref names,
    so no working preview build is lost.
  - Item 3 changes the error text and status source for an identity that
    would already have been refused; previously it was refused with a pattern
    message.
- **Resource impact.** Negligible: one extra regexp match per create-tenant
  and a segment loop per preview-deploy.
- **Risks and mitigations.**
  - The stricter `isConstrained` could flag existing parameters. Mitigation:
    the implementer runs the test first and adds `MaxLength` to each flagged
    parameter, matching its documented bound or the template's limit.
  - `git_ref` tightening might refuse an unusual ref someone uses. Mitigation:
    the table-driven tests cover common branch, tag and SHA shapes, and the
    rule is a subset of `git check-ref-format`.
- **Cross-repo.** No mctl-gitops change is required. A follow-up to widen
  `creator_user_id` on both sides is suggested under Open questions.

## Open questions

- Which ZITADEL `preferred_username`/`email` shapes real users have, in
  particular `+`. This could not be observed here. If any real user has one,
  widen `CreatorUserIDPattern` and `wft-create-tenant.yaml` together, and
  quote the `userId` splice.
- The `MaxLength` for `human_input_responses`: 65536 is proposed, and
  mctl-agents should confirm the DevLoop's real ceiling.
