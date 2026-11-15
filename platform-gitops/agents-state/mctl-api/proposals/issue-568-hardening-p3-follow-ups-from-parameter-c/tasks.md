# Tasks: issue-568-hardening-p3-follow-ups-from-parameter-c

- [ ] 1. Normalize the `host` that `mctl_deploy_service` sends. In `toolDeployService`'s handler (`internal/mcp/server.go`), after the `none`/`auto` default block, replace a non-empty `params["host"]` with `normalizeDomain(...)`. Update the `normalizeDomain` doc comment to cover deploy-service. — DoD: an MCP call with `host: "API.Example.com."` posts `host=api.example.com`, and the default `none`/`auto` behaviour is unchanged.
- [ ] 2. Add `normalizeIdentifier` (trim plus lowercase) to `internal/mcp`, with a comment that it mirrors `internal/api.normalizeIdentifier`, and optionally reuse it in `normalizeTenantArg`. Apply it to `team` and `service` in `toolRemoveCustomDomain` and `toolVerifyDomain`, right after they are read. — DoD: the list query, the delete call and both `wfParams` maps carry the lowercase, trimmed values.
- [ ] 3. In `registry.go`, export `CreatorUserIDPattern = ^[A-Za-z0-9._@-]{1,256}$`. Use it for `creator_user_id`, change the description to "Authenticated user ID of the workspace creator (set by the server from the session; never caller-supplied)", and add a comment that it mirrors `wft-create-tenant.yaml`'s unquoted-splice guard. — DoD: the registry builds and the description is updated.
- [ ] 4. (depends on 3) In `internal/api/handlers_write.go`, where `input["creator_user_id"] = user.ID` is set, check `user.ID` against the compiled `operations.CreatorUserIDPattern`. On a mismatch, write a `denied` audit entry and answer 400 with a message naming the sign-in identity format. Replace the "prevent spoofing" comment with an accurate one. — DoD: a session ID like `alice+x@example.com` gets the explicit 400 before `ValidateInput`, and valid IDs are unaffected.
- [ ] 5. Add `MaxLength: 65536` to `human_input_responses` (`registry.go`, `mctl-agents-investigate`). — DoD: a value over 65536 bytes is refused by `ValidateInput`.
- [ ] 6. (depends on 5) Tighten `isConstrained` in `internal/operations/registry_constraints_test.go`. For a parameter without an Enum, require an anchored Pattern AND either `MaxLength > 0` or no unbounded repetition in the parsed regexp (`regexp/syntax`: `OpStar`, `OpPlus`, `OpRepeat` with `Max == -1`). Add `MaxLength` to any existing parameter the new rule flags. — DoD: `TestEveryWorkflowParameterIsConstrained` and `TestConstraintCheckFailsWhenAnyConstraintIsRemoved` pass, and the synthetic test reports an anchored-but-unbounded pattern.
- [ ] 7. Share one repo-relative-path rule. Export `RepoPathPattern` (each segment may start with one optional `.`, then `[A-Za-z0-9_]`) and `RepoPathMaxLength = 256` from `internal/operations`, and use them for both `dockerfile_path` parameters. In `internal/api/handlers_ci_deploy.go`, derive `ciDockerfilePathRe` from `operations.RepoPathPattern`, add a length check in `ciRelativePath`, keep the segment loop, and fix both comments. — DoD: `.docker/Dockerfile` passes both gates; `.`, `..`, `../x`, `/abs`, `-x`, `a//b` and `a/-b` fail both.
- [ ] 8. Export `operations.HostnameLabelPattern` and derive `internal/api`'s `hostnameLabelPattern` from it (`"^" + ... + "$"`). — DoD: there is one literal source left in the repo for the label regex.
- [ ] 9. Fix the stale `serviceEnumOperationToTool` comment (and any repeat in the `TestServiceEnumsMatchRegistry` doc) in `internal/mcp/server_test.go`. It should say that `mctl-agents-incidents` is excluded because `mctl_trigger_incident_responder` exposes no `service` argument, even though the registry declares the Enum. — DoD: the comment matches `registry.go:801` and the tool schema.
- [ ] 10. Tighten `git_ref`. Add `gitRefPattern = ^[A-Za-z0-9_](\.?[A-Za-z0-9_-])*(/[A-Za-z0-9_](\.?[A-Za-z0-9_-])*)*$` and set `MaxLength: 255` on `preview-deploy` `git_ref`. Add an op-specific check in `Registry.ValidateInput` that refuses a `git_ref` segment ending in `.lock`. — DoD: a leading `-`, `..`, `//`, a trailing `/` or `.`, a segment starting with `.`, and `.lock` are all refused; SHAs, `v1.2.3`, `feat/x-y` and `release/2026.11` still pass.
- [ ] 11. Verify that the `MaxLength int32` rationale comment is present on `ParameterDef` (`registry.go:74-76`), and make no code change. — DoD: noted in the PR description as already satisfied.
- [ ] 12. (depends on 1-10) Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. — DoD: everything is green, and the MCP tool count in `server_test.go` is unchanged.

## Tests

- [ ] T1. `internal/mcp`: a deploy-service handler test with a fake API that captures the posted body. `host` values `API.Example.com.`, ` auto `, `AUTO`, and a missing host for base-service and for worker-service give `api.example.com`, `auto`, `auto`, `auto` and `none`.
- [ ] T2. `internal/mcp`: remove-domain (legacy fallback path) and verify-domain tests with `team: " Labs "` and `service: "API"`. The captured `wfParams`, the list query and the delete call carry `labs`/`api`.
- [ ] T3. `internal/api`: a create-tenant test with a session `user.ID` of `alice+x@example.com` returns 400 with the identity-format message, writes a `denied` audit entry and submits no workflow. A valid login still succeeds.
- [ ] T4. `internal/operations`: `ValidateInput` refuses an oversized `human_input_responses`. `TestConstraintCheckReportsSyntheticAndUnanchored` gains a `(?s)^\[.*\]$` case with no MaxLength, which is now reported, and the same case with a MaxLength is not.
- [ ] T5. A table test in both `internal/operations` (the `RepoPathPattern` regexp) and `internal/api` (`ciRelativePath`) asserts identical verdicts for `Dockerfile`, `.docker/Dockerfile`, `docker/prod.Dockerfile`, `.`, `..`, `../x`, `a/../b`, `/abs`, `-x`, `a//b`, `a/-b` and a 257-byte path.
- [ ] T6. `internal/api`: `hostnameLabelPattern.String() == "^" + operations.HostnameLabelPattern + "$"`, plus a label table (`a`, `xn--p1ai`, `a-b`, `-a`, `a-`, `A`, a 63-character and a 64-character label).
- [ ] T7. `internal/operations`: a `git_ref` table through `ValidateInput` for `preview-deploy`. Accepted: a 40-hex SHA, `main`, `v1.2.3`, `feat/x-y`, `release/2026.11`. Refused: `-x`, `a..b`, `a//b`, `a/`, `a.`, `.a`, `a/.b`, `x.lock`, `a.lock/b`, and a 256-byte value.
- [ ] T8. The existing `TestServiceEnumsMatchRegistry`, `TestEveryWorkflowParameterIsConstrained` and the tool-count test still pass.

## Rollback

Every change is in mctl-api code only, with no stored state, migrations or
gitops changes. Revert the PR and redeploy the previous mctl-api image tag
(for example with `mctl_rollback_service` or the usual Helm values revert).
Inputs that were newly accepted (normalized hosts and identifiers, dotfile
Dockerfile paths) go back to being refused, and inputs that were newly refused
(malformed `git_ref`, segments starting with `-` on the CI path) go back to
being accepted. Neither direction leaves anything to clean up.
