# Tasks: issue-748-feat-mcp-read-only-agent-asset-index-and

- [ ] 1. Gitops reader for agent-platform data: add `internal/gitops/agent_platform.go` with the `AgentPlatformProfile`, `ExecutionProfileSpec`, `AgentPlatformPolicy`, `AgentPlatformRelease` and `AgentPlatformSnapshot` types, `ListAgentPlatformProfiles`, `GetAgentPlatformPolicy`, `ListAgentPlatformReleases` and `ReadAgentPlatformSnapshot`. All read under `r.mu.RLock()`, return `revisionLocked()`, `Lstat` every file (non-regular is an error), check `kind`, refuse duplicate profile names, and wrap parse errors with the relative path. Optional numeric and bool fields are pointers. — DoD: `go test ./internal/gitops/...` passes. A malformed file errors, a missing directory returns an empty list plus the revision, and an unsynced checkout errors.
- [ ] 2. Extend the `GitReader` interface (`internal/api/interfaces.go`) with `ReadAgentPlatformSnapshot()` and add stub methods to the fakes in `internal/api/smoke_test.go` and `internal/api/build_repo_gate_internal_test.go` (depends on 1). — DoD: `go build ./... && go vet ./...` is clean.
- [ ] 3. Pure check engine in `internal/api/agent_preflight.go`: the `PreflightCheck` type, the `ruleSources` table (check id to `validate-agent-platform.py:<line>` or `agentregistry`), the nine checks listed in requirements.md, and `verdict()`. Missing input gives `unknown` with a reason; there is no error-to-pass path (depends on 1). — DoD: table-driven unit tests cover pass, fail and unknown for every check id.
- [ ] 4. Factor selector parsing out of `ResolveBinding` (`handlers_agent_platform.go`) into `parseBindingSelector`, with no behaviour change. — DoD: the existing `ResolveBinding` tests pass unchanged.
- [ ] 5. `internal/api/handlers_agent_assets.go`: `ListAgentAssets` (per-source status, data `null` when unavailable, reverse refs from `ok` sources only, `gitops_revision`) and `PreflightAgent` (registry resolve; fall back to gitops on the not-found sentinels only; the `release-intent`, `explicit` and `naming-convention` selections; `binding.*` unknown on any other registry error; 404 when no profile). Both start with `requireAgentRegistryAdmin`, and return 503 when both the registry and `GitReader` are nil (depends on 2, 3, 4). — DoD: handler tests (T4-T9) pass.
- [ ] 6. Routes in `internal/api/router.go`: `r.Get("/agent-assets", h.ListAgentAssets)` and `r.Get("/agents/{name}/preflight", h.PreflightAgent)` in the v1alpha2 block, with a comment. Add both to the route pin in `router_test.go` (depends on 5). — DoD: router tests pass; `/agents/{name}/bindings/resolve` and the other routes are unaffected.
- [ ] 7. MCP tools in `internal/mcp/server.go`: `toolListAgentAssets` and `toolPreflightAgent` as thin `s.apiGet` forwarders (`url.PathEscape(agent)`, `url.Values` for the selectors), with title, `WithReadOnlyHintAnnotation(true)` and `WithDestructiveHintAnnotation(false)`, registered after `toolResolveAgent` (around `:339`). Add `mctl_preflight_agent` to `ungovernedAgentTools` in `agent_receipt_gate.go` (depends on 6). — DoD: `TestAgentReceiptGate_ClassifiesEveryTool` passes.
- [ ] 8. Bookkeeping: bump the tool count in `internal/mcp/server_test.go`. Add both tools to `annotations_test.go` (expectation map and read-only list) and to `docs/portal-allowlist.json` (`enabled: false`, with a reason modelled on `mctl_list_agents`). Add a short section to `docs/agent-platform-registry.md` describing both endpoints and the "no eligibility semantics" invariant (depends on 7). — DoD: `go test ./internal/mcp/...` passes, and `golangci-lint run` is clean.
- [ ] 9. Release and verify (depends on 8). — DoD: after deploy, `mctl_preflight_agent agent_name=issue-investigator environment=production` returns `source: gitops`, `selection: naming-convention`, a `gitops_revision`, nine checks and a verdict (expected `unknown` until a production binding exists), and `mctl_list_agent_assets` returns all five sources.

## Tests

Each test must go red under the named mutation.

- [ ] T1. `internal/gitops` reader tests (temp checkout fixture, as in the existing reader tests):
  - a malformed `profile.yaml` makes `ListAgentPlatformProfiles` return an error naming the file (mutation: `continue` on a parse error);
  - a malformed `policy.yaml` gives an error;
  - a symlinked `profile.yaml` gives an error;
  - a missing `agent-platform/` gives an empty list plus the revision;
  - an unsynced checkout gives an error;
  - the snapshot reports one revision for all parts, and a per-part error does not blank the other parts.
- [ ] T2. `agent_preflight` unit tests: every check id in pass, fail and unknown. `budgetUsd` 30 against `maxBudgetUsd` 25 gives `profile.budget: fail` (mutation: compare against `maxTimeoutSeconds` or a wrong field). An absent `budgetUsd` gives `unknown`. A mutating scope with `requiresApproval: merge` and no gate gives `fail`. Provider `mctl-api` with alias `other` gives `fail`. `enabled: true` without `mcp__mctl__*` gives `fail`.
- [ ] T3. `verdict()`: {pass, fail} gives fail; {pass, unknown} gives unknown; all pass gives pass; an empty list gives unknown (mutation: default to pass).
- [ ] T4. Handler: a nil `policy.yaml` with an error in the snapshot makes the `profile.budget`, `timeout`, `sandbox`, `model_policy_task`, `refs` and `approval_gates` checks `unknown`, and the verdict is not `pass` (mutation: treat a read error as an empty policy). This runs with `AgentRegistry` nil and a fake `GitReader`, so it needs no DB.
- [ ] T5. Handler: a non-admin caller gets 403 on both endpoints (mutation: drop `requireAgentRegistryAdmin`).
- [ ] T6. Handler: reverse refs. Two gitops profiles both listing skill `mctl-platform` make `refs.skills["mctl-platform"]` contain both (mutation: overwrite instead of append). The same holds for policyRef.
- [ ] T7. Handler: an unavailable source is `null` with `status: unavailable` and a reason, never `[]`; the other sources still `ok`, with HTTP 200.
- [ ] T8. Handler: selector 400s match `ResolveBinding`'s (both selectors, neither, half pin). An environment with no intent falls back to `<agent>-default` with `selection: naming-convention`. No profile gives 404.
- [ ] T9. Handler (`TEST_DATABASE_URL`-gated, `newTestAgentPlatformStore`): a published binding resolves with `source: agentregistry` and `binding.lifecycle: pass`. A not-found binding falls back to gitops.
- [ ] T10. New `internal/mcp/agent_assets_test.go` uses the table-of-paths pattern from `commerce_test.go:35`: `mctl_list_agent_assets` maps to `GET /api/v1/agent-assets`; `mctl_preflight_agent` with environment maps to `GET /api/v1/agents/issue-investigator/preflight?environment=production`; an explicit pin forwards all three params; an agent name with `/` is escaped.
- [ ] T11. `annotations_test.go`: both tools pinned `readOnly: true, destructive: false` (mutation: drop the hint). `portal_allowlist_test.go`: both listed, `enabled: false`.

## Rollback

All changes are additive and read-only: two GET routes, two MCP tools, new reader methods, and no DB or schema change. To roll back, revert the PR (or redeploy the previous mctl-api image tag with `mctl_rollback_service`). No data migration or cleanup is needed. If only the MCP exposure is a problem, removing the two `srv.AddTool` lines (and their allowlist, annotation and gate entries) disables the tools while keeping the REST endpoints.
