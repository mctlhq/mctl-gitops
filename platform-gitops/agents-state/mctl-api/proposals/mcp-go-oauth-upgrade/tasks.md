# Tasks: mcp-go-oauth-upgrade

- [ ] 1. Bump `github.com/mark3labs/mcp-go` to `v0.49.0` in `go.mod` and run
  `go mod tidy` — DoD: `go.mod` pins `mcp-go v0.49.0`; `go.sum` is
  consistent; `go build ./...` completes with zero errors on CI.

- [ ] 2. Resolve any compilation errors caused by API surface changes between
  v0.31 and v0.49 (depends on 1) — DoD: all call sites in `internal/mcp/`
  and any other package that imports mcp-go compile cleanly; no use of
  deprecated or removed symbols; changes are limited to adapter/init code and
  do not touch tool handler logic.

- [ ] 3. Configure RFC 9728 Protected Resource Metadata in the server
  initializer (depends on 2) — DoD: the mcp-go server is constructed with the
  `ProtectedResourceMetadata` (or equivalent) option populated with
  `Resource = "https://api.mctl.ai/mcp"`,
  `AuthorizationServers = ["https://ops.mctl.me/api/dex"]`, and
  `BearerMethodsSupported = ["header"]`; `GET
  https://api.mctl.ai/mcp/.well-known/oauth-protected-resource` returns HTTP
  200 with a valid JSON body containing those three fields.

- [ ] 4. Audit existing auth middleware for `WWW-Authenticate` header
  interference (depends on 2) — DoD: code review confirms no middleware
  overwrites or strips the `WWW-Authenticate` header emitted by mcp-go on 401
  responses; if a conflict is found it is resolved and documented in the PR
  description.

- [ ] 5. Run the full 24-tool MCP Inspector validation pass (depends on 3, 4)
  — DoD: MCP Inspector reports zero schema errors, zero missing tools, and
  zero changed tool signatures across all 24 tools; Inspector output is
  attached to the pull request as a CI artifact.

- [ ] 6. Load test the Streamable HTTP endpoint on staging (depends on 5) —
  DoD: a 10-minute load test at representative RPS shows no silent frame drops,
  no HTTP 5xx errors attributable to transport issues, and p99 latency within
  10% of the pre-upgrade baseline; results attached to the PR.

- [ ] 7. Update `context/current-version.md` after merge and create a new ADR
  entry if the upgrade required non-trivial call-site changes (depends on
  merge) — DoD: `current-version.md` reflects v4.15.0 (or the next patch
  version chosen by the release process); if an ADR is warranted it is
  committed in `context/decisions/` and references ADR 0001.

## Tests

- [ ] T1. Unit test: `GET /mcp/.well-known/oauth-protected-resource` returns
  HTTP 200 with `Content-Type: application/json` and a body containing
  `resource`, `authorization_servers`, and `bearer_methods_supported` fields
  with the expected values.

- [ ] T2. Unit test: unauthenticated `POST /mcp` returns HTTP 401 with a
  `WWW-Authenticate` header containing `resource_metadata=` pointing to the
  well-known URL (validates task 4 does not strip the header).

- [ ] T3. Integration test: invoke each of the 24 tools via the MCP test
  harness with a valid PKCE token and assert the response structure is
  unchanged from the pre-upgrade snapshot (schema regression guard).

- [ ] T4. Integration test: invoke each of the 24 tools with an expired token
  and assert the 401 error body contains structured metadata that a
  RFC 9728-compliant client can parse to re-initiate the PKCE flow.

- [ ] T5. CI gate: MCP Inspector run (headless) against the upgraded binary;
  must exit 0, blocking merge on any schema discrepancy (implements the ADR
  0001 re-validation requirement).

- [ ] T6. Load test (staging only): 10-minute Streamable HTTP session
  sustaining 50 concurrent tool calls per minute; assert zero frame-loss
  events in structured logs and p99 latency within 10% of baseline.

## Rollback
1. Revert the `go.mod` / `go.sum` change to `mcp-go v0.31.0` and any
   associated call-site adapter changes via `git revert <merge-commit>`.
2. Trigger a new ArgoCD sync from the reverted commit in mctl-gitops; the
   previous binary (v4.14.0 or whichever was current) is redeployed to the
   `admins` tenant automatically.
3. Verify rollback by confirming MCP Inspector passes against the restored
   binary and that the Claude.ai connector reconnects successfully.
4. The RFC 9728 well-known endpoint will disappear after rollback; no client
   data is lost because the endpoint is stateless and additive.
5. File a post-mortem issue capturing which API surface change or test failure
   triggered the rollback, to inform the next upgrade attempt.
