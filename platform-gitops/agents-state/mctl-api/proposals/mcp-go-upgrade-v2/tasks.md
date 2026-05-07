# Tasks: mcp-go-upgrade-v2

- [ ] 1. Bump `mark3labs/mcp-go` to v0.52.0 and tidy — run
  `go get github.com/mark3labs/mcp-go@v0.52.0 && go mod tidy`. — DoD: `go.mod` lists
  `github.com/mark3labs/mcp-go v0.52.0`; `go.sum` is consistent; no unintended transitive
  dependency changes appear in the diff.

- [ ] 2. Resolve all compile-time errors (depends on 1) — run `go build ./...` and fix every
  breaking API change introduced between v0.31 and v0.52.0. Expected areas: tool registration
  signatures, server option structs, transport initialisation, `CallToolResult` type. — DoD:
  `go build ./...` succeeds with zero errors and zero new vet warnings.

- [ ] 3. Re-validate and fix all 24 tool input schemas (depends on 2) — for each of the 24
  registered MCP tools, verify the `InputSchema` accurately reflects accepted parameters and
  types. Fix any inaccuracies. Enable per-tool SEP-1303 server-side validation where
  available. — DoD: all 24 tools have valid JSON Schema definitions; no well-formed tool call
  is incorrectly rejected; a tool call with an invalid parameter returns JSON-RPC error
  `-32602` before the handler runs.

- [ ] 4. Run the full unit test suite (depends on 2) — DoD: `go test ./...` passes with no
  new failures.

- [ ] 5. Memory regression test on staging (depends on 2) — deploy the upgraded binary to
  staging and send 1 000 sequential MCP tool calls. Observe `go_goroutines` and
  `go_memstats_heap_inuse_bytes` in Prometheus before and after the load. — DoD: goroutine
  count returns to pre-test baseline (within ±5%) after the load completes; no unbounded heap
  growth is observed.

- [ ] 6. Validate OAuth 2.0 PKCE flow in staging (depends on 2) — run the full Claude.ai
  connector PKCE authentication flow against the staging `/mcp` endpoint. — DoD: Claude.ai
  connector successfully authenticates and the tool listing is returned.

- [ ] 7. Run MCP Inspector against staging (depends on 3, 5, 6) — execute the upstream MCP
  Inspector tool against the staging `/mcp` endpoint. — DoD: all 24 tools pass schema
  validation and spec compliance; no JSON-RPC violations are reported.

- [ ] 8. govulncheck verification (depends on 1) — DoD: `govulncheck ./...` reports zero
  findings attributable to `mark3labs/mcp-go`; the output is attached to the PR.

- [ ] 9. Deploy to `admins` production via ArgoCD (depends on 7, 8) — merge the updated
  image tag to the gitops repository and sync. — DoD: ArgoCD reports `Healthy` and `Synced`;
  pods restart cleanly; `go_goroutines` and heap metrics remain stable for 15 minutes
  post-deploy; MCP error rate (`mcp_tool_errors_total`) shows no spike.

## Tests

- [ ] T1. `go test ./...` — full unit suite passes on the upgraded dependency.
- [ ] T2. MCP Inspector — all 24 tools pass schema and spec validation on staging.
- [ ] T3. Schema rejection test — a tool call with a missing required parameter returns
  JSON-RPC `-32602` without invoking the handler.
- [ ] T4. PKCE flow test — Claude.ai connector authenticates end-to-end in staging.
- [ ] T5. Memory / goroutine leak test — 1 000 sequential tool calls; goroutine count
  returns to baseline (within ±5%) after the burst.
- [ ] T6. `govulncheck ./...` — zero CVE findings for mcp-go.
- [ ] T7. Post-deploy Prometheus check — `go_goroutines` and heap metrics stable for 15
  minutes; `mcp_tool_errors_total` shows no regression.

## Rollback
ArgoCD's automated sync will revert to the previous image tag if the readiness probe fails.
Manual rollback procedure:
1. In the mctl-gitops repository, revert the `mctl-api` image tag to the last known-good
   release and push to main.
2. `argocd app sync mctl-api` — ArgoCD deploys the previous image.
3. Confirm `/healthz` returns HTTP 200 and `go_goroutines` stabilises.
4. The HTTP body leak remains present in the rollback version. Apply a temporary mitigation:
   set a shorter pod restart policy (e.g., memory limit with `requests == limits`) to
   contain goroutine accumulation until the fix is re-attempted.
5. Record the rollback in the incident log and schedule a re-attempt with the compile errors
   fully triaged.
