# Tasks: issue-417-add-newton-mcp-gateway-to-the-devloop-se

- [ ] 1. Append `"newton-mcp-gateway"` as the last element of the four DevLoop
      `service` enums in `internal/operations/registry.go` — the
      `ParameterDef` for `service` on `mctl-agents-implement` (line ~661),
      `mctl-agents-shepherd` (line ~695), `mctl-agents-approve` (line ~753) and
      `mctl-agents-reconcile` (line ~789). Keep every existing value and its
      position; the three optional params keep their leading `""`.
      — DoD: `grep -c '"newton-mcp-gateway"' internal/operations/registry.go`
      prints `4`; the `mctl-agents-single-service` enum at line ~620 is
      byte-identical to before and still has exactly 8 values.

- [ ] 2. Append `"newton-mcp-gateway"` as the last argument of the four
      `mcplib.Enum(...)` mirrors in `internal/mcp/server.go` —
      `mctl_trigger_implementer` (line ~2800), `mctl_trigger_shepherd`
      (line ~2841), `mctl_trigger_reconcile` (line ~2886) and
      `mctl_trigger_approve` (line ~2985) — in the same order as task 1.
      (depends on 1)
      — DoD: `grep -c '"newton-mcp-gateway"' internal/mcp/server.go` prints `4`;
      the `mctl_trigger_single_service` enum at line ~2743 is unchanged with 8
      values; no tool is added or removed.

- [ ] 3. Append `"newton-mcp-gateway"` to `wantServices` in
      `internal/operations/registry_test.go` (line ~26), after `".github"`.
      (depends on 1)
      — DoD: `wantServices` has 16 entries ending in `".github",
      "newton-mcp-gateway"`; no other line of the file changes.

- [ ] 4. Run the repo's gates: `go fmt ./...` (must produce no diff),
      `go build ./...`, `go vet ./...`, `go test ./...`, `golangci-lint run`.
      (depends on 2, 3)
      — DoD: all five are clean; `git diff --stat` touches exactly three files
      (`internal/operations/registry.go`, `internal/mcp/server.go`,
      `internal/operations/registry_test.go`) with 9 changed lines total.

- [ ] 5. Open the PR referencing mctl-api#417, noting in the body that #274
      (deriving the list from one place) is deliberately untouched.
      (depends on 4)
      — DoD: PR open, CI green, description links #417 and states the
      nine-site scope.

## Tests

No new test files are needed — the existing guards are already driven off the
fixture edited in task 3. Verify each of them actually exercises the new value:

- [ ] T1. `go test ./internal/operations/ -run TestApproveAcceptsEveryMctlAgentsService -v`
      shows a passing `newton-mcp-gateway` subtest. This is the exact
      `Registry.ValidateInput` path that returned the 400 for `portfolio`
      (#281) and `seerrsense` (#306).
- [ ] T2. `go test ./internal/operations/ -run TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`
      passes — confirms `newton-mcp-gateway` is present in all four registry
      enums (forward direction) and that no enum carries a value missing from
      `wantServices` (reverse direction).
- [ ] T3. `go test ./internal/mcp/ -run TestServiceEnumsMatchRegistry` passes —
      confirms the live `tools/list` schema for all four tools matches the
      registry enums value-for-value **and in order**, i.e. the new value was
      appended at the same index on both sides.
- [ ] T4. `go test ./internal/mcp/` passes in full — in particular the MCP tool
      count expectation in `server_test.go` is unchanged, proving no tool was
      accidentally added.
- [ ] T5. Negative check: confirm a value that is still not registered (e.g.
      `service=not-a-service`) is still rejected by `ValidateInput` on
      `mctl-agents-approve`, i.e. the enum was widened by exactly one entry and
      not removed. Covered by the existing suite; assert by inspection of the
      diff if no direct test exists.
- [ ] T6. Post-merge smoke: call `mctl-agents-approve` (or
      `mctl_trigger_approve`) with `service=newton-mcp-gateway` and the real
      proposal slug and confirm it no longer 400s at the API edge. Note that
      mctl-agents itself must also have the repo in `config/settings.py`; a
      failure past the edge is an mctl-agents issue, not a regression here.

## Rollback

The change is three files, append-only, with no state or schema migration.
Revert the merge commit (`git revert -m 1 <sha>`) and redeploy the previous
`mctl-api` image tag — or use `mctl_rollback_service` with the prior tag for
the running service. Behaviour returns exactly to today's: every previously
valid service keeps working and `service=newton-mcp-gateway` starts 400ing
again on the four DevLoop operations, leaving any newton-mcp-gateway proposal
un-approvable until the change is re-landed. No data is written or destroyed by
this change, so a revert has no cleanup step. If a partial state is ever
suspected (e.g. only some enums deployed), the grep counts in tasks 1-3 tell
you which side a running build is on.
