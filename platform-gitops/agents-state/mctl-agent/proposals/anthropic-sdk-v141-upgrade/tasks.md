# Tasks: anthropic-sdk-v141-upgrade

- [ ] 1. Audit current Anthropic SDK usage — DoD: a comment in the implementation PR
  lists every file and function in `internal/` that imports or calls the Anthropic SDK
  or the custom MCP scaffolding, including the `LLMDiagnosis` skill, the `POST /mcp`
  handler, and any webhook middleware; the list is complete and accurate.

- [ ] 2. Bump `anthropic-sdk-go` to v1.41.0 and tidy the module (depends on 1) — DoD:
  `go.mod` references `github.com/anthropics/anthropic-sdk-go v1.41.0`; `go mod tidy`
  and (if vendored) `go mod vendor` complete without error; `go build ./...` exits 0;
  `go vet ./...` reports no issues.

- [ ] 3. Migrate the MCP tool registry to SDK-provided helpers (depends on 2) — DoD:
  all 6 existing MCP tools are re-registered using the SDK's MCP tool builder; the
  hand-rolled JSON-RPC dispatcher is removed; `POST /mcp` returns well-formed JSON-RPC
  responses for all 6 tools in manual or automated tests.

- [ ] 4. Migrate webhook signature verification to the SDK's built-in handler (depends
  on 2) — DoD: custom HMAC middleware is replaced with the SDK's `webhook.ValidateRequest`
  (or equivalent); a unit test with a known-good signed payload returns HTTP 200 and a
  known-bad signature returns HTTP 401.

- [ ] 5. Update `LLMDiagnosis` call sites to v1.41.0 API (depends on 2) — DoD: all
  deprecated method signatures are replaced with their v1.41.0 equivalents; the
  diagnose pipeline produces the same output as before for a fixed test prompt; no
  timeout regression.

- [ ] 6. Add or update tests for equivalence of replaced scaffolding (depends on 3, 4,
  5) — DoD: for each removed custom code path, a table-driven or stub-based test
  confirms that the SDK replacement produces equivalent output; overall test coverage of
  the MCP handler does not decrease.

- [ ] 7. Open a PR to `mctlhq/mctl-agent` (depends on 6) — DoD: PR description
  references this proposal slug, links to the anthropic-sdk-go v1.41.0 release notes,
  summarises what custom code was removed and what SDK feature replaced it, and includes
  CI green status.

- [ ] 8. Deploy to staging and measure RSS before/after (depends on 7) — DoD: RSS
  reported by `kubectl top pod` for mctl-agent in the staging namespace is within 10 MB
  of the pre-upgrade baseline; result is recorded in the PR description.

## Tests

- [ ] T1. `go build ./...` and `go vet ./...` pass on the bumped dependency tree.
- [ ] T2. Unit: each of the 6 MCP tools returns the same JSON-RPC response structure
  (tool name, output schema) as before the migration — verified by snapshot comparison.
- [ ] T3. Unit: a valid signed Anthropic webhook request is accepted (HTTP 200); an
  unsigned or tampered request is rejected (HTTP 401) by the new SDK handler.
- [ ] T4. Unit: `LLMDiagnosis` skill calls the Anthropic API with a stubbed transport
  and produces a diagnosis string matching the pre-upgrade format.
- [ ] T5. Integration (optional staging): `POST /mcp` with a `list_tools` JSON-RPC
  request returns all 6 tool names with correct schemas against the running pod.
- [ ] T6. Regression: all pre-existing tests in `internal/skill/builtin/` continue to
  pass without modification.

## Rollback
If the upgraded SDK causes a regression in the diagnose phase or the MCP endpoint:

1. Revert the `go.mod` / `go.sum` changes and re-vendor (if applicable) by reverting
   the PR to `mctlhq/mctl-agent`.
2. Release a patch version restoring the previous custom scaffolding.
3. The `LLMDiagnosis` skill's circuit breaker will auto-disable it after N consecutive
   failures — manually re-enable after the rollback deploy confirms stable operation.
4. File a post-mortem identifying which SDK API changed unexpectedly, add a regression
   test, and schedule a re-attempt with the corrected migration.
