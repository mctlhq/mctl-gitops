# Tasks: issue-569-feat-commerce-receipt-read-and-mcp-tools

- [ ] 1. Add `internal/commerce/receipt.go` with `PolicyDecisionRef` (status constants
  `none`, `recorded`, `missing`, `unavailable`), the explicit `Receipt` struct and pure
  `ReceiptOf(Invocation, PolicyDecisionRef) Receipt` - DoD: the struct has no
  `idempotency_key`, `args_digest`, `provider_operation_key`, `version` or reservation
  fields; all amounts are `int64` minor units; `schema_version` is `commerce.SchemaVersion`;
  `go vet` clean.
- [ ] 2. (depends on 1) Add `policyDecisionOf` and `GetCommerceReceipt` to
  `internal/api/handlers_commerce.go`, reusing `requireCommerceTenant(...,
  "commerce-invocation-read")`, `Store.GetInvocation` and `writeCommerceError`; map approval
  read results to the four statuses via `h.opts.WorkItems.ActionApproval` and
  `workitems.ErrApprovalNotFound` - DoD: a foreign tenant, a foreign invocation and a
  missing id all produce 404 `not found`; an approval-store failure yields 200 with
  `policy_decision.status = "unavailable"`.
- [ ] 3. (depends on 2) Mount `r.Get("/invocations/{invocation_id}/receipt",
  h.GetCommerceReceipt)` under the tenant subtree in `internal/api/router.go` - DoD: route
  reachable behind the same auth middleware as `GET /invocations/{invocation_id}`.
- [ ] 4. (depends on 3) Document the route in `internal/openapi/openapi.yaml` with a
  `CommerceReceipt` schema and add the path to `internal/openapi/embed_test.go`; update the
  "Routes" table and add a "Receipts" section in `docs/commerce-ledger.md` - DoD:
  `go test ./internal/openapi/...` passes.
- [ ] 5. Add `internal/mcp/commerce.go` with `toolGetCommerceBudget`,
  `toolListCommerceInvocations`, `toolGetCommerceReceipt`: tenant and id validation before
  any request, `url.Values` query building, path escaping, calls through the existing
  `workItemCall` helper (caller's token, API status and body preserved), read-only and
  non-destructive annotations - DoD: tools compile and return API bodies verbatim on 2xx.
- [ ] 6. (depends on 5) Register the three tools in `NewMCPServer` (`internal/mcp/server.go`)
  - DoD: `mcpSrv.ListTools()` includes them.
- [ ] 7. (depends on 6) Add the three names to `recordedHints` and to
  `TestReadOnlyToolsAreTheRecordedSet` in `internal/mcp/annotations_test.go`, and add three
  `"enabled": false` entries with tool-specific reasons (>= 40 chars after the provenance
  sentence) to `docs/portal-allowlist.json` - DoD: `TestNewMCPServer_ToolCount`,
  `TestReadOnlyToolsAreTheRecordedSet` and `TestPortalAllowlist_CoversEveryRegisteredTool`
  pass.
- [ ] 8. (depends on 1-7) Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`,
  `go test ./...` - DoD: all clean; DB-backed tests run with `TEST_DATABASE_URL` set.

## Tests

- [ ] T1. `internal/commerce/receipt_test.go`: `ReceiptOf` on a fully populated
  `Invocation` (every optional field set) marshals to exactly the allowlisted JSON key set;
  a test fails if `idempotency_key`, `args_digest`, `provider_operation_key`,
  `authorization_id`, `capture_id` or `external_ref` appears.
- [ ] T2. `receipt_test.go`: every numeric money field decodes as a JSON integer (no `.`),
  and `schema_version` equals `SchemaVersion`.
- [ ] T3. Handler test (DB-backed, `TEST_DATABASE_URL`): tenant owner reads the receipt of
  its own invocation -> 200 with the five facts, `quote_digest`, `terms_version`, `phase`,
  `execution_id`.
- [ ] T4. Handler test: tenant A reading tenant B's real invocation id, tenant A reading a
  nonexistent id, and a caller without access to `{tenant}` all get 404 with byte-identical
  bodies.
- [ ] T5. Handler test: `policy_decision` is `none` without approval; `recorded` with the
  approval's `policy_rule_id`/`policy_version` when present; `missing` when the approval id
  does not resolve; `unavailable` when `WorkItems` is nil.
- [ ] T6. Handler test: ledger unconfigured -> 503; caller with no principal -> 403
  `identity-unresolved`; caller below `commerceTenantRole` -> refused as for sibling reads.
- [ ] T7. `internal/mcp/commerce_test.go` with an `httptest` server: each tool hits the
  expected path and query (capability URI encoded), forwards the caller token, returns the
  body on 200, and returns the same tool error text for two different 404 causes.
- [ ] T8. MCP argument validation: missing `tenant`, a `tenant` with `/` or `..`, and a
  malformed `invocation_id` return a tool error and make no HTTP request.
- [ ] T9. Regression: existing `GET .../invocations` and `GET .../invocations/{id}`
  responses carry no `external_ref` key and no argument/result payload fields.

## Rollback

The change is additive and needs no migration. Revert the PR and redeploy the previous
mctl-api image: the receipt route and the three MCP tools disappear, and no stored data is
touched. If only the MCP tools are a problem, they ship disabled on the shared portal
already; leaving `docs/portal-allowlist.json` at `enabled: false` hides them there without a
code revert. `COMMERCE_DISABLED` turns every commerce route, the receipt included, into 503
as an emergency switch.
