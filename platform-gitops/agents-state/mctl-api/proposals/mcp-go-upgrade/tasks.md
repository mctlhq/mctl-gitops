# Tasks: mcp-go-upgrade

- [ ] 1. Bump `mark3labs/mcp-go` to v0.50.0 — run `go get github.com/mark3labs/mcp-go@v0.50.0 && go mod tidy`. — DoD: `go.mod` lists `v0.50.0`; `go.sum` is consistent.
- [ ] 2. Resolve compile errors (depends on 1) — address all breaking API changes surfaced by `go build ./...`. Typical areas: tool registration signatures, server option structs, transport initialisation. — DoD: `go build ./...` succeeds with zero errors.
- [ ] 3. Audit and fix tool input schemas (depends on 2) — for each of the 24 registered MCP tools, verify the `InputSchema` accurately describes all accepted parameters and constraints. Fix any schema inaccuracies found. — DoD: all 24 tools have valid JSON Schema definitions; no schema produces a false validation rejection on a well-formed call.
- [ ] 4. Enable SEP-1303 input schema validation (depends on 3) — enable the opt-in per-tool validation feature introduced in v0.50.0. — DoD: a tool call with an invalid parameter (e.g., wrong type, missing required field) is rejected with JSON-RPC error `-32602` before the handler is invoked.
- [ ] 5. Validate OAuth 2.0 PKCE flow (depends on 2) — in a staging environment, run the full PKCE flow for the Claude.ai connector against `https://api.mctl.ai/mcp`. — DoD: Claude.ai connector successfully authenticates and lists tools.
- [ ] 6. Run MCP Inspector against staging (depends on 4, 5) — execute the upstream MCP Inspector tool against the staging `/mcp` endpoint. — DoD: all 24 tools pass schema validation; no JSON-RPC spec violations reported.
- [ ] 7. Deploy to `admins` staging (depends on 6) — build and push the updated image; update ArgoCD manifest. — DoD: ArgoCD reports `Healthy` and `Synced`; readiness probe passes.
- [ ] 8. Deploy to `admins` production (depends on 7) — merge manifest to gitops main. — DoD: production pods restart cleanly; no increase in MCP error rate for 15 minutes post-deploy.

## Tests

- [ ] T1. `go test ./...` — full unit test suite passes.
- [ ] T2. MCP Inspector — all 24 tools pass schema and spec validation on staging.
- [ ] T3. Schema rejection test — a crafted tool call with an invalid parameter returns JSON-RPC `-32602` without invoking the handler.
- [ ] T4. PKCE flow test — Claude.ai connector authenticates end-to-end in staging.
- [ ] T5. `govulncheck ./...` — zero CVE findings attributable to mcp-go.

## Rollback
ArgoCD automated sync policy will revert to the previous image tag if readiness fails. Manual rollback: `argocd app rollback mctl-api --revision <previous>`. The MCP tool contract is unchanged externally — Claude.ai and Claude Code clients will reconnect to the previous version transparently. No database migrations involved.
