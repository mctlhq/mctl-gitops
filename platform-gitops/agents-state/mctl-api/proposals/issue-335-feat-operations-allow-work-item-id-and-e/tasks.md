# Tasks: issue-335-feat-operations-allow-work-item-id-and-e

- [ ] 1. Add `work_item_id` and `execution_id` to the `mctl-agents-investigate`
      entry in `internal/operations/registry.go` (the `builtinOperations`
      element around line 633). Both `Type: "string"`, `Required: false`, no
      `Default` field, `Pattern: ^[A-Za-z0-9_.-]{1,128}$`, with descriptions
      stating they are passed through unchanged and not resolved by mctl-api.
      — DoD: `issue_url` is untouched; `RiskLevel`, `AdminOnly`,
      `WorkflowTemplate`, `ModifiesPaths` unchanged; `go build ./...` passes.
- [ ] 2. Add a code comment above the two new entries (depends on 1) recording
      why they are optional and un-defaulted, the consumer
      (`mctlhq/mctl-agents#267`), the CWFT half (`mctlhq/mctl-gitops#1279`),
      and the fact that `ApplyDefaults` forwards `""` when they are omitted so
      the CWFT must treat empty as absent. — DoD: comment cites both issue
      numbers and the empty-string contract, matching the style of the
      neighbouring `approver` comment on `mctl-agents-approve`.
- [ ] 3. Extend the operation's `Description` string with one sentence:
      optionally accepts `work_item_id` / `execution_id` for work-item
      correlation, ignored when absent (depends on 1). — DoD: `GET
      /api/v1/operations` and `mctl_get_operation mctl-agents-investigate`
      render the sentence; no other operation's description changes.
- [ ] 4. Run the repo gates: `go fmt ./...`, `go vet ./...`,
      `golangci-lint run`, `go test ./...` (depends on 1-3). — DoD: all clean,
      including `internal/mcp` (the tool-count expectation in
      `internal/mcp/server_test.go` must be unaffected — no MCP tool is added
      or removed by this change).
- [ ] 5. Post-merge verification against the live platform (depends on 4):
      one `mctl_trigger_issue` submit against a throwaway issue with the two
      identifiers supplied, then `mctl_get_workflow_status`. — DoD: HTTP 202,
      the workflow reaches `Running`/`Succeeded` rather than failing Argo spec
      validation, and the submitted parameters appear in the audit entry. If
      it fails spec validation, revert (see Rollback) and land
      `mctlhq/mctl-gitops#1279` first.
- [ ] 6. Comment on `mctlhq/mctl-agents#267` and `mctlhq/mctl-gitops#1279`
      (depends on 5) stating that the API half is live, naming the two
      accepted parameters and the empty-string-means-absent contract. — DoD:
      both issues carry the note, so the consumer does not have to read this
      repo to learn the contract.

## Tests

- [ ] T1. `TestInvestigateAcceptsResumeIdentifiers` in
      `internal/operations/registry_test.go`: `ValidateInput` on
      `mctl-agents-investigate` returns no errors for
      `{issue_url, work_item_id: "wi_5c8e...", execution_id: "we_9a01..."}`
      and also for `{issue_url}` alone. Assert both new `ParameterDef`s have
      `Required == false` and `Default == ""` — a default would fabricate a
      correlation ID, which is the failure this pins (same shape as
      `TestReconcileDefaultsToWriting`).
- [ ] T2. `TestInvestigateRejectsMalformedResumeIdentifiers` in the same file:
      `ValidateInput` with `work_item_id: "wi_ bad;rm -rf /"` returns exactly
      one error naming `work_item_id`, and a valid engine-style reference
      (`dev-loop-mctlhq-mctl-api-227`) as `execution_id` returns none.
- [ ] T3. `TestInvestigateStripUndeclaredKeepsResumeIdentifiers` in the same
      file: `StripUndeclared` on the investigate operation keeps both new keys
      and still drops an undeclared one (`config_patch`), with the dropped
      slice naming it.
- [ ] T4. Handler-level test in `internal/api` (new
      `handlers_write_investigate_test.go`, using `newTestRouter` /`postAs`
      from `smoke_test.go` and `exec.submittedParams`, mirroring
      `handlers_write_undeclared_test.go`): POST
      `/api/v1/operations/mctl-agents-investigate/execute` as `adminUser` with
      all three parameters returns 202 and the executor receives all three
      values byte-for-byte unchanged.
- [ ] T5. Same file: POST with only `issue_url` returns 202 and the executor
      receives `issue_url` unchanged — the "behaves exactly as today"
      criterion — while `work_item_id`/`execution_id` are present only as
      empty strings (the `ApplyDefaults` behaviour this design accepts, pinned
      so a future change to it is a deliberate one).
- [ ] T6. Same file: POST with an undeclared key alongside the three valid
      parameters returns 202 and the undeclared key never reaches the
      executor; POST with `work_item_id` containing a space returns 400 with a
      `validationErrors` entry naming the parameter.
- [ ] T7. Non-admin regression: POST as a non-admin user still returns 403
      even with the new parameters supplied — the `AdminOnly` gate is
      unaffected by the wider parameter set.

## Rollback

Single-commit revert of the registry change; redeploy mctl-api. There is no
migration, no persisted state and no gitops manifest to unwind, and the
operation returns to declaring only `issue_url`.

Two caveats for whoever pulls the trigger:

- Reverting **before** `mctlhq/mctl-gitops#1279` and `mctlhq/mctl-agents#267`
  land is free — nothing consumes the values yet.
- Reverting **after** they land does not fail loudly. `StripUndeclared` drops
  the identifiers and the investigation runs un-resumed; the only signal is
  the warn line `ignoring undeclared operation parameters` with
  `operation=mctl-agents-investigate`. If a rollback is needed at that point,
  watch that line (or pause the resume path in `#267`) rather than assuming
  submits are failing.
