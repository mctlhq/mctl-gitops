# Tasks: issue-836-feat-whoami-report-the-bound-tenant-of-a

- [ ] 1. In `internal/api/handlers_read.go` `Whoami`, build the response map and add `"boundTenant"` only when `user.BoundTenant()` returns ok. Extend the comment to state that the field is informational. — DoD: bound support user gets the key, all other principals do not; `id/groups/isAdmin/namespaces` unchanged.
- [ ] 2. In `internal/mcp/server.go` `toolWhoami`, add `BoundTenant` to the decode struct and print `Bound tenant: <t>` after the existing lines when non-empty. — DoD: unbound output byte-identical to today.
- [ ] 3. In `toolWhoami`, replace `_ = json.Unmarshal` with an error check returning `mcplib.NewToolResultError("Failed to read identity: ...")` and logging via `slog.Error`, without echoing the body. — DoD: malformed body yields `IsError: true` and no `User:` line.
- [ ] 4. Update the `mctl_whoami` description to mention the bound tenant and that a tenant-bound token can act only on that tenant. — DoD: description text updated; `go test ./internal/mcp/...` passes (annotations/portal allowlist tests unaffected).
- [ ] 5. Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...`. — DoD: all clean.

## Tests
- [ ] T1. `internal/api/handlers_whoami_test.go`: add `BoundTenant string \`json:"boundTenant"\`` to `whoamiResponse` (or decode into `map[string]any` for key-presence checks). A new test calls `callWhoami` with `auth.NewAgentUser("mctl-support", auth.AgentRun{Scope: auth.AgentScopeSupport, Tenant: "labs"})` and asserts `boundTenant == "labs"`. The test must fail if the field is removed.
- [ ] T2. Same file, table test asserting the `boundTenant` key is absent (decoded as `map[string]any`) for: a human user with groups, an admin, `NewAgentUser("issue-investigator", AgentRun{Scope: AgentScopeInvestigate})`, an unscoped agent, and a support-scope agent with an empty tenant.
- [ ] T3. `internal/mcp/whoami_test.go`: with a backend returning `{"id":"agent:mctl-support","groups":[],"isAdmin":false,"namespaces":[],"boundTenant":"labs"}`, `callWhoamiViaMCP` returns no error and the text contains `Bound tenant: labs`.
- [ ] T4. Same file: with a backend returning a body without `boundTenant` (reuse the `mashkovd` fixture), the text contains no `Bound tenant` line.
- [ ] T5. Same file: a backend that returns 200 with a malformed body (e.g. `{not json`) makes `callWhoamiViaMCP` return `isError == true`, and the text does not contain `User:`.
- [ ] T6. Optional: assert the `mctl_whoami` tool description mentions the bound tenant.

## Rollback
Revert the single PR. The change is additive (a conditional JSON key and a text line) plus a decode error check, with no data, schema, or config changes, so reverting and redeploying mctl-api restores the previous behaviour. mctl-support keeps working either way, because its 0.2.1 prompt workaround does not depend on the field.
