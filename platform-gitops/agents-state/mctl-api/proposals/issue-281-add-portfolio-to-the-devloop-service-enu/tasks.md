# Tasks: issue-281-add-portfolio-to-the-devloop-service-enu

- [ ] 1. Confirm the exact literal against mctlhq/mctl-agents `config/settings.py`
      SERVICES (`portfolio` vs `mctl-portfolio`) and use that string everywhere.
      Proceed with the issue's literal `"portfolio"` if the file is not reachable —
      DoD: the chosen string is recorded in the PR description with its source.
- [ ] 2. `internal/operations/registry.go` — append `"portfolio"` to the end of the
      `service` parameter `Enum` for `mctl-agents-implement` (line ~596),
      `mctl-agents-shepherd` (~628), `mctl-agents-approve` (~671) and
      `mctl-agents-reconcile` (~707), preserving existing order and the leading `""`
      on the three optional filters (depends on 1) — DoD:
      `grep -c '"portfolio"' internal/operations/registry.go` prints `4`, and the
      `mctl-agents-single-service` enum (~557) and `mctl-agents-incidents` service
      param (~577) are byte-identical to `main`.
- [ ] 3. `internal/mcp/server.go` — append `"portfolio"` to the `mcplib.Enum(...)` call
      for `service` in `toolTriggerImplementer` (~2658), `toolTriggerShepherd` (~2699),
      `toolTriggerReconcile` (~2744) and `toolTriggerApprove` (~2787) (depends on 1) —
      DoD: `grep -c '"portfolio"' internal/mcp/server.go` prints `4`, the
      single-service enum at ~2601 is unchanged, and no tool is added or removed.
- [ ] 4. Extend `wantServices` in
      `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`
      (`internal/operations/registry_test.go:29`) with `"portfolio"` and update the
      doc comment to cite mctl-api#281 next to the 2026-08-05 mctl-design incident
      (depends on 2) — DoD: the test fails on a `main` checkout of `registry.go` and
      passes with task 2 applied.
- [ ] 5. Add `TestApproveAcceptsPortfolioService` to
      `internal/operations/registry_test.go`: call
      `NewRegistry().ValidateInput(op, map[string]string{"service": "portfolio",
      "slug": "issue-281-add-portfolio"})` on `mctl-agents-approve` (depends on 2) —
      DoD: the returned error slice is empty; the test names the returned errors on
      failure.
- [ ] 6. Add `TestServiceEnumsMatchRegistry` to `internal/mcp/server_test.go` beside
      the `operationToTool` fixture (line ~845): for the four DevLoop
      operation/tool pairs, read `tools[].inputSchema.properties.service.enum` from a
      live `tools/list` response (same `mcpSrv.HandleMessage` + `json.Unmarshal`
      pattern as line ~879) and assert exact, order-sensitive equality with the
      registry `ParameterDef.Enum`. Exclude `mctl-agents-single-service` and
      `mctl-agents-incidents` with an inline comment explaining why (depends on 2, 3) —
      DoD: the test passes on the full change and fails if `"portfolio"` is reverted
      from either file alone.
- [ ] 7. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
      `go test ./...` (depends on 2-6) — DoD: all clean; in particular
      `TestNewMCPServer_ToolCount`, `TestAllToolsHaveTitleAnnotation` (74 tools) and
      `TestPortalAllowlist_CoversEveryRegisteredTool` still pass with no edit to
      `docs/portal-allowlist.json`.
- [ ] 8. Open the PR titled `feat(agents): add portfolio to DevLoop service enums`,
      linking #281 and noting that #274 remains open for the structural fix
      (depends on 7) — DoD: PR body lists the eight changed sites and states that no
      refactor was attempted.

## Tests

- [ ] T1. `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices` — `portfolio`
      present in the `service` enum of all four DevLoop operations.
- [ ] T2. `TestApproveAcceptsPortfolioService` — `ValidateInput` on
      `mctl-agents-approve` with `service: "portfolio"` returns zero errors
      (acceptance criterion 2, the exact path that produced the 400).
- [ ] T3. `TestServiceEnumsMatchRegistry` — the four registry enums equal the four MCP
      tool enums element-by-element, and `mctl_trigger_approve`'s live `tools/list`
      enum contains `portfolio` (acceptance criteria 3 and the anti-drift guard).
- [ ] T4. Regression: `go test ./internal/operations/... ./internal/mcp/...` green
      (acceptance criterion 1), including the unchanged 74-tool count assertions and
      the portal allowlist guard.
- [ ] T5. Manual/CI check: `grep -c '"portfolio"' internal/operations/registry.go` = 4
      and `grep -c '"portfolio"' internal/mcp/server.go` = 4 (acceptance criterion 4).
- [ ] T6. `golangci-lint run` passes (acceptance criterion 5).

## Rollback

The change is additive and confined to two source files plus two test files. To roll
back, revert the single commit (`git revert <sha>`) and redeploy the previous mctl-api
image tag with `mctl_rollback_service` — no migration, no gitops state, no persisted
data is involved. After a rollback, `mctl-agents-approve` again returns
`400 service: must be one of ...` for `portfolio`, i.e. the pre-change behaviour and the
failure described in the issue; any `portfolio` proposal already flipped to `accepted`
stays accepted, since the enum only gates new requests. A partial revert (one file only)
is explicitly not a valid state — `TestServiceEnumsMatchRegistry` will fail — so revert
both source files together.
