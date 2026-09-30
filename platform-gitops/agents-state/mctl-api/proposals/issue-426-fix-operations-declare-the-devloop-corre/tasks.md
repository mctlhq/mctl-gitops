# Tasks: issue-426-fix-operations-declare-the-devloop-corre

- [ ] 1. Transcribe `spec.arguments.parameters` from the three mctl-agents
      ClusterWorkflowTemplates in `mctlhq/mctl-gitops`
      (`cwft-mctl-agents-investigate` per mctl-gitops#1345,
      `cwft-mctl-agents-implement` and `cwft-mctl-agents-shepherd` per #1418)
      into a reviewed list, noting per template whether it declares
      `temporal_workflow_id`, `temporal_run_id`, `execution_request_id`,
      `work_item_id`, `execution_id`, and any default value each has.
      — DoD: an exact per-operation name list exists in the PR description or a
      commit message, sourced from the manifests (not inferred), and resolves
      the requirements.md open question about shepherd's set. Any name the CWFT
      does **not** declare is excluded from task 2.

- [ ] 2. Add `devLoopCorrelationParams(names ...string) []ParameterDef` to
      `internal/operations/registry.go`, next to `agentPinParams`
      (registry.go:98), plus the two pattern constants `temporalIDPattern`
      (`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`, mirroring
      `internal/usage/types.go:286`) and `correlationIDPattern`
      (`^[A-Za-z0-9_-]{1,64}$`, the shape investigate already uses). Every
      returned `ParameterDef` is `Required: false`, `Default: ""`,
      `OmitWhenEmpty: true`, with a `Pattern` and a `Description` saying the id
      is opaque and omitting it is normal. (depends on 1)
      — DoD: helper compiles; doc comment cites mctlhq/mctl-api#426 and
      mctlhq/.github#50, states "opaque — nothing here resolves, mints or
      defaults them", and explains the `OmitWhenEmpty` rationale by reference to
      the `ParameterDef` comment at registry.go:68-77.

- [ ] 3. Append `devLoopCorrelationParams(...)` to the three operations in
      `builtinOperations`, using exactly the names task 1 confirmed:
      `mctl-agents-investigate` (registry.go:718-733),
      `mctl-agents-implement` (registry.go:660-666),
      `mctl-agents-shepherd` (registry.go:686-700). Leave investigate's existing
      `work_item_id` / `execution_id` definitions untouched. (depends on 2)
      — DoD: `go build ./...` passes; no existing parameter, enum, pattern,
      `RiskLevel`, `AdminOnly` or `ModifiesPaths` value on any of the three
      operations is modified; `issue_url` is still `Required: true`.

- [ ] 4. Update `internal/api/handlers_write_devloop_params_test.go`: remove the
      three correlation rows from `devLoopParamsPendingDeclaration` (line 162),
      keeping the `human_input_responses` row and the table itself, and add the
      matching rows to `devLoopSubmissions` (line 27) — one investigate row with
      pin + `work_item_id` + `execution_id` + `temporal_workflow_id` +
      `temporal_run_id` + `execution_request_id`, one `dev_loop.py` implement row
      and one `_shepherd_tick` row with pin + the four names their CWFTs declare.
      Annotate each new row with its mctl-agents sender, as the existing rows
      are. (depends on 3)
      — DoD: `TestExecuteOperation_PendingDevLoopParamsAreStillStripped` passes
      with only `human_input_responses` remaining;
      `TestExecuteOperation_DevLoopParamsAreNeverDropped` passes with the new
      rows; the pre-existing minimal rows (directive poller,
      `implement_sweep.py`, reconcile, incidents, approve) are unchanged.

- [ ] 5. Add `internal/operations/registry_cwft_params_test.go` with
      `cwftDeclaredParams` (the task-1 transcription, with provenance comments
      naming mctl-gitops#1345 / #1418) and
      `cwftParamsNotSettableViaAPI` (CWFT parameters mctl-api deliberately does
      not declare, each with a non-empty reason string). (depends on 1, 3)
      — DoD: the inventory is a faithful transcription; every exemption has a
      stated reason; the file's doc comment states plainly what the guard can
      catch (a transcribed CWFT parameter never declared in the registry) and
      what it cannot (a CWFT parameter added in gitops that nobody transcribed),
      in the style of `registry_test.go:39-54`.

- [ ] 6. Extend `docs/agent-platform-registry.md` — in or beside the "Release
      pins on `mctl-agents-*` operations" section (line 343) — with a "DevLoop
      correlation parameters" subsection: the per-operation table of names and
      their mctl-agents sender, the opaque-data statement, the `OmitWhenEmpty`
      rationale, the gitops-first ordering rule, and a pointer to the guard test
      and its inventory as the place to edit when a CWFT parameter changes.
      (depends on 3, 5)
      — DoD: doc reflects exactly what the code declares; no stale claim that
      the correlation parameters are stripped.

- [ ] 7. Run the full gate: `go fmt ./...`, `go vet ./...`, `golangci-lint run`,
      `go test ./...`. (depends on 4, 5, 6)
      — DoD: all clean. In particular `internal/mcp` is untouched, so the tool
      count in `internal/mcp/server_test.go` still matches; if it does not,
      something outside this proposal's scope was changed and must be reverted.

- [ ] 8. Post-deploy verification. Trigger one DevLoop run
      (`mctl_trigger_issue` with `use_temporal=true`) and read the resulting
      `mctl-agents-investigate-*` workflow. (depends on 7)
      — DoD: the workflow's `spec.arguments.parameters` contains
      `temporal_workflow_id`, `temporal_run_id` and `execution_request_id` with
      the DevLoop's real values; the server log line "ignoring undeclared
      operation parameters" no longer names them; and
      `GET /api/v1/usage/summary?group_by=temporal_workflow_id` shows new rows
      bucketed under a real workflow id rather than an empty bucket — the
      mctlhq/.github#50 criterion, evidenced.

## Tests

- [ ] T1. `TestDevLoopCorrelationParamsSurviveStripUndeclared` in
      `internal/operations/registry_test.go`: for each of the three operations,
      `StripUndeclared` keeps every declared correlation parameter unchanged
      while an undeclared `config_patch` in the same input is still dropped and
      reported as the only entry in `dropped`. Mirrors
      `TestInvestigateForwardsReleasePin` (registry_test.go:422).
- [ ] T2. `TestDevLoopCorrelationParamsAreOmittedWhenEmpty`: for each of the
      three operations, `ApplyDefaults({})` and
      `ApplyDefaults({"temporal_workflow_id": "", ...})` leave every correlation
      key absent from the map. Mirrors `TestReleasePinIsOmittedWhenEmpty`
      (registry_test.go:507).
- [ ] T3. `TestDevLoopCorrelationParamPatterns`: table-driven accept/reject over
      `ValidateInput`. Accept the observed live shapes —
      `temporal_workflow_id=dev-loop-mctlhq-mctl-agents-494`,
      `temporal_workflow_id=dev-loop-xr_0000`,
      `temporal_run_id=00000000-0000-0000-0000-000000000000`,
      `execution_request_id=xr_0000`. Reject `"a b"`, a value with an embedded
      `\n`, `"x; rm -rf /"`, a 200-character value, and a leading `-`. Mirrors
      `TestInvestigateRejectsMalformedResumeIdentifiers` (registry_test.go:343).
- [ ] T4. `TestDevLoopCorrelationParamsStayOptional`: none of the new parameters
      is `Required`, none has a non-empty `Default`, all have `OmitWhenEmpty`
      true and a non-empty `Pattern`; and `ValidateInput` on
      `{"issue_url": <valid>}` alone still returns no errors.
- [ ] T5. `TestCWFTParamsAreDeclaredOrExplicitlyInternal` (task 5): per
      operation, every name in `cwftDeclaredParams` is either declared by the
      operation or carries a non-empty reason in `cwftParamsNotSettableViaAPI`;
      plus the converse, that every exemption names a parameter the inventory
      actually lists, so dead exemptions cannot accumulate.
- [ ] T6. The updated tables in
      `internal/api/handlers_write_devloop_params_test.go` (task 4) are
      themselves the end-to-end test: they drive the real router as
      `auth.NewServiceUser()` and assert the values arrive at
      `exec.submittedParams`, which is the only assertion that proves the
      parameters reach Argo rather than merely existing in the registry.
- [ ] T7. Regression: extend the
      `TestExecuteOperation_UnpinnedCallerSendsNoAgentImage` pattern (or add a
      sibling) so a caller sending none of the correlation parameters produces a
      submission whose parameter map contains none of their keys — the
      byte-identical-to-today guarantee for the directive poller and
      `implement_sweep.py`.

## Rollback

The change is additive, stateless and confined to one Go package plus tests and
one doc, so rollback is a plain revert with no cleanup:

1. **Revert the commit** (`git revert`) and redeploy the previous mctl-api image
   via the normal gitops image-tag bump. `StripUndeclared` immediately resumes
   dropping the correlation parameters and warn-logging them; every caller goes
   back to today's behaviour. Nothing persisted the ids, so no data needs
   undoing — usage rows already written with correlation values stay valid and
   simply stop being produced.
2. **Faster partial rollback, if only one operation misbehaves**: delete that
   operation's `devLoopCorrelationParams(...)` append (task 3) and move its rows
   back into `devLoopParamsPendingDeclaration` (task 4). The other two keep
   working; this is the preferred response if a single CWFT turns out not to
   declare a name that was transcribed wrongly.
3. **If the DevLoop breaks because Argo rejects a submit** (an undeclared-by-CWFT
   name was forwarded), the symptom is a failed `mctl-agents-*` workflow, not a
   silent one — visible via `mctl_get_workflow_status` /
   `mctl_list_recent_agent_runs`. Roll back per step 2 for the affected
   operation; do not attempt to fix it forward in gitops under time pressure,
   since the mctl-api side is the reversible half.
4. **No coordination with mctl-gitops is required to roll back.** The CWFTs
   declare these parameters as optional and already tolerate their absence —
   that is the state production is in today.
