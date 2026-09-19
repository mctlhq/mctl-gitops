# Tasks: issue-335-feat-operations-allow-work-item-id-and-e

- [ ] 1. Add the two optional parameters to the `mctl-agents-investigate` entry
      in `internal/operations/registry.go` (the `Parameters` slice at lines
      649-651): `work_item_id` and `execution_id`, both
      `Type: "string"`, `Required: false`, no `Default`, and
      `Pattern: ^[A-Za-z0-9_-]{1,64}$`. — DoD: both entries present, `issue_url`
      byte-for-byte unchanged, and nothing else in the `Operation` literal
      (`RiskLevel`, `AdminOnly`, `WorkflowTemplate`, `ModifiesPaths`) touched.
- [ ] 2. Write the in-code comment above the two entries (depends on 1)
      explaining *why* they are declared: `StripUndeclared`
      (`registry.go:160-176`) drops undeclared keys before Argo, the consumer is
      `mctlhq/mctl-agents#267`, the CWFT half is `mctlhq/mctl-gitops#1279`, and
      mctl-api neither mints nor resolves these ids. — DoD: a reader who has
      never seen #335 can tell from the file alone why an optional,
      pattern-only, store-less parameter is correct here; matches the commentary
      density of the surrounding entries.
- [ ] 3. Point the parameter `Description` strings at
      `docs/work-context-contract.md` for the id scheme (`wi_<uuid>` /
      `we_<uuid>`) and state that omitting them yields a cold issue-driven run
      (depends on 1). — DoD: `GET /api/v1/operations/mctl-agents-investigate`
      returns descriptions a caller can act on without reading the Go source.
- [ ] 4. Verify Argo tolerates workflow-level arguments the referenced
      ClusterWorkflowTemplate does not declare (depends on 1) — submit one
      investigate run against a cluster where `mctl-agents-investigate` has not
      yet taken `mctlhq/mctl-gitops#1279`, and confirm the Workflow is created
      and runs with `work_item_id=""` / `execution_id=""` present in
      `spec.arguments.parameters`. — DoD: the result is recorded on the PR. If
      Argo rejects it, the PR is held until gitops#1279 merges, or extended to
      omit empty-valued optional parameters for this operation before
      `Executor.Submit`.
- [ ] 5. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
      `go test ./...` (depends on 1-3, per `CLAUDE.md`). — DoD: all clean; in
      particular `internal/mcp` tests still pass unchanged, since no MCP tool is
      added or removed and the tool-count expectation in
      `internal/mcp/server_test.go` must not move.
- [ ] 6. Confirm no other surface needs editing (depends on 1): the generic
      `/operations/{name}/execute` request body has no OpenAPI schema in
      `internal/openapi/openapi.yaml`, and `mctl_trigger_issue`
      (`internal/mcp/server.go:2995`) is deliberately left alone per the
      proposal's out-of-scope list. — DoD: a note on the PR stating both, so a
      reviewer does not read the omission as an oversight.

## Tests

All new tests go in `internal/operations/registry_test.go`, following
`TestReconcileDefaultsToWriting`'s convention of asserting both the declared
struct fields and the behaviour a caller actually reaches.

- [ ] T1. `TestInvestigateAcceptsResumeIdentifiers` — `ValidateInput` on
      `mctl-agents-investigate` with
      `{issue_url, work_item_id: "wi_5c8e1f2b-...", execution_id: "we_9a01..."}`
      returns zero errors. This is the acceptance criterion "the two parameters
      are accepted" exercised through the same function the handler calls.
- [ ] T2. `TestInvestigateResumeIdentifiersStayOptional` — `ValidateInput` with
      only `issue_url` returns zero errors, and `ApplyDefaults` on that input
      yields `work_item_id == ""` and `execution_id == ""`, pinning "no invented
      default". Also assert both `ParameterDef`s have `Required == false` and
      `Default == ""`.
- [ ] T3. `TestInvestigateForwardsResumeIdentifiers` — `StripUndeclared` with
      `{issue_url, work_item_id, execution_id, config_patch}` keeps the first
      three with their values intact and returns `["config_patch"]` as dropped.
      This is the "forwards them" and "a parameter outside the declared set is
      still rejected" pair in one assertion, at the exact function
      `handlers_write.go:83` calls.
- [ ] T4. `TestInvestigateRejectsMalformedResumeIdentifiers` — `ValidateInput`
      returns an error naming the parameter for values carrying shell or
      whitespace metacharacters (`"wi_x; rm -rf /"`, `"we_a b"`, a 100-character
      id, a value with a newline), and no error for the plain documented forms.
- [ ] T5. `TestInvestigateStillRequiresIssueURL` — `ValidateInput` with only
      `work_item_id` and `execution_id` still reports
      `missing required parameter: issue_url`, so adding resume identifiers did
      not turn the issue URL optional by accident.
- [ ] T6. Handler-level check in `internal/api`: POST
      `/api/v1/operations/mctl-agents-investigate/execute` as an admin with all
      three parameters yields a submitted workflow whose captured params contain
      all three unchanged (reuse the fake executor harness used by
      `internal/api/handlers_write_undeclared_test.go`, which already captures
      submitted params). Same request as a non-admin still gets 403.

## Rollback

Single-commit, single-file revert. The change is two struct literals in
`internal/operations/registry.go` plus tests — `git revert <sha>` and redeploy
restores the previous registry exactly: `issue_url` again becomes the only
declared parameter, and `StripUndeclared` resumes dropping `work_item_id` /
`execution_id` on the way to Argo. No migration to undo, no persisted state, no
gitops file written by this change, and no API removal that could break a
caller — a client that had started sending the two parameters returns to the
pre-change behaviour (silently dropped, run proceeds cold) rather than erroring.

Rollback trigger to watch after deploy: any `mctl-agents-investigate` Workflow
failing at creation time with an argument-related error (the risk named in
design.md under Platform impact). In that case prefer rolling forward by
merging `mctlhq/mctl-gitops#1279` — which declares the parameters on the CWFT —
over reverting, since the revert leaves mctl-agents#267 blocked.
