# Tasks: issue-196-feat-governance-agent-execution-identity

- [ ] 1. Write `docs/adr/011-execution-identity-contract.md` — the
  `ExecutionContext` schema table, the closed vocabularies, the per-field
  trust table (control-plane-asserted vs workload-declared), the versioning
  rule, the relationship to ADR 007 (`AgentDefinition`), ADR 009
  (`ContextSnapshot.ExecutionCorrelation`) and ADR 010 (`Executor`), and the
  normative sentence "execution identity is never authorization".
  DoD: ADR merged in the house style (status, date, issue, Context, Decision,
  Alternatives, Non-goals, Platform impact, Implementation map), cross-linked
  from `docs/adr/009-context-snapshot-contract.md` and
  `docs/agent-inventory.yaml`.
- [ ] 2. Add `orchestrator/execution_identity.py` (depends on 1) — stdlib-only
  module with `API_VERSION = "identity.mctl.ai/v1alpha1"`, `KIND`,
  `SUPPORTED_API_VERSIONS`, the vocabulary `frozenset`s, frozen dataclasses
  `Actor`, `Executor`, `Scope`, `Trigger`, `Correlation`, `Assertions`,
  `ExecutionContext`, each with `to_dict`/`from_dict`, plus `seal(...)`,
  `validate(parent=None)`, `recompute_content_hash()`, `to_log_dict()` and
  `ExecutionIdentityError(ValueError)`.
  DoD: `uv run mypy` and `uv run ruff check` clean; module imports nothing
  outside the stdlib; unknown `api_version`, unknown key and out-of-vocabulary
  value all raise.
- [ ] 3. Add `ExecutionContext.to_execution_correlation()` (depends on 2)
  returning a `context_snapshot.ExecutionCorrelation`, so ADR 009's block is a
  projection rather than a second hand-built copy.
  DoD: round-trip test asserts every `ExecutionCorrelation` field is populated
  from the context; `orchestrator/context_snapshot.py` is not modified.
- [ ] 4. Add `load_from_environment()` and `mint_local()` (depends on 2) —
  read `MCTL_EXECUTION_CONTEXT_FILE`; when absent, fail closed if
  `MCTL_REQUIRE_EXECUTION_CONTEXT` is set, otherwise return a locally sealed
  context with `actor.verification = "unverified"` and
  `assertions.asserted_by = "local"`.
  DoD: both branches covered by tests; no exception escapes into a driver on
  the local path.
- [ ] 5. Add `orchestrator/temporal/activities/identity.py` (depends on 2) —
  `MintRequest`/`MintedContext` dataclasses and
  `@activity.defn mint_execution_context`, sealing the document and `POST`ing
  it to `/api/v1/agents/executions/context` with the `httpx` + `auth_headers()`
  pattern of `orchestrator/temporal/activities/state.py`; `trace_id` derived
  deterministically inside the activity from `temporal_workflow_id` + run id.
  DoD: registered on the control worker in `orchestrator/temporal/worker.py`
  next to `record_execution`; a non-2xx response degrades to a returned
  unverified context instead of raising.
- [ ] 6. Mint in `DevLoopWorkflow` (depends on 5) — a root context on entry and
  one child per step (investigate, approve, implement, review-fix) sharing one
  `trace_id`, all inside the single `workflow.patched("execution-identity")`
  funnel; failures handled like `_record` (best-effort, never fail the loop).
  DoD: `tests/test_dev_loop_workflow.py` asserts one mint per step, stable
  `trace_id`, and that a mint failure does not change the loop's outcome.
- [ ] 7. Propagate across the Argo boundary (depends on 6) — add
  `execution_context_id` and `trace_id` to the `params` dict in `_run_cwft`'s
  four call sites (`dev_loop.py:812`, `:897`, `:950`, `:1264`) and to
  `workflows/incidents.py:128`.
  DoD: a unit test asserts both keys are present in every
  `SubmitAndWaitInput.params` the loop produces, and that no other key changed.
- [ ] 8. Extend the ledger (depends on 5) — add `execution_context_id` and
  `trace_id` to `ExecutionRecord`
  (`orchestrator/temporal/activities/state.py:28-44`) and the
  `/api/v1/agents/executions` payload, with empty-string defaults so an older
  mctl-api keeps accepting the row.
  DoD: `tests/test_temporal_activities.py` asserts the two new keys in the
  posted body and that `_record` still never fails the workflow.
- [ ] 9. Attach identity to tool and MCP calls (depends on 4) — add
  `X-Mctl-Execution-Context` and `X-Mctl-Trace-Id` to the headers built by
  `mctl_mcp_config` (`orchestrator/options.py:15-54`), and include the context
  id in the `AUDIT` line emitted by `_audit_pre_tool_use` (`options.py:224`).
  DoD: headers are present when a context is loaded and absent (not empty)
  when it is not; `MCTL_TOKEN`-unset behaviour is unchanged;
  `orchestrator/validate_manifest.py`'s options-vs-manifest comparison still
  passes.
- [ ] 10. Record identity on the proposal (depends on 4) — add a read-only
  `execution:` block (`context_id`, `trace_id`, `agent`, `version`) to
  `write_status_yaml`'s payload (`run_issue_investigator.py:987-1000`) and
  extend `_status_disagreements` (`:539-582`) to verify it survived
  publication; do the same for `run_implementer.update_status_yaml`.
  DoD: `.status.yaml` gains the block, `proposal_state.update_status_file`
  preserves it across transitions, and no approval/authorization semantics are
  attached to it.
- [ ] 11. Load and log the context in the drivers (depends on 4, 9) —
  `run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py` call
  `load_from_environment()` once and emit
  `[identity] execution_context=<json>` via `to_log_dict()`, mirroring
  `ExecutionPlan.log()` (`resolver.py:290`).
  DoD: exactly one identity line per run; no secret, issue body, or token
  appears in it.
- [ ] 12. Document the sibling changes (depends on 1) — a short
  "Cross-repo prerequisites" section naming the mctl-api storage endpoint plus
  the two new ledger columns, and the mctl-gitops CWFT parameter declarations
  and context-file injection.
  DoD: follow-up issues opened for mctl-api and mctl-gitops, referenced from
  the ADR's Implementation map; the mctl-agents side works (degraded) without
  either.

## Tests

- [ ] T1. Schema round-trip and sealing: `seal()` fills `content_hash` and
  `context_id = "ex-" + content_hash[7:23]`, `to_dict`/`from_dict` is lossless,
  and a golden fixture
  (`tests/fixtures/identity/investigator-context.json`) is asserted
  byte-for-byte stable, in the style of
  `tests/test_context_snapshot.py::test_golden_fixture_hash_is_stable`.
- [ ] T2. Fail-closed validation: unknown `api_version`, unknown key, missing
  required field, and every out-of-vocabulary `actor.type`, `trigger.type`,
  `workflow_type`, `environment`, `executor.type` raise
  `ExecutionIdentityError`; each vocabulary member is accepted via
  `@pytest.mark.parametrize` over the `frozenset`.
- [ ] T3. Non-authorization guard: a recursive field-name assertion that no
  `allow`/`deny`/`permit`/`grant`/`authorized`/`role` token appears anywhere in
  the serialized schema.
- [ ] T4. Import isolation: a `subprocess.run([sys.executable, "-c", ...])`
  check that importing `orchestrator.execution_identity` loads no
  `claude_agent_sdk`, `temporalio`, `httpx`, `yaml`, `anyio` or `mcp`, using
  the `tests/test_worker_isolation.py` pattern.
- [ ] T5. Step chaining: a child context must share its parent's `trace_id`,
  reference `parent_context_id`, and have a strictly increasing
  `step_sequence`; a mismatch raises.
- [ ] T6. Propagation: every `SubmitAndWaitInput.params` produced by
  `DevLoopWorkflow` contains `execution_context_id` and `trace_id`; the
  `ExecutionRecord` payload contains both; `mctl_mcp_config` emits both
  headers.
- [ ] T7. Degraded modes: no `MCTL_EXECUTION_CONTEXT_FILE` yields an
  `unverified` local context; `MCTL_REQUIRE_EXECUTION_CONTEXT=1` makes the
  same case raise; a mint activity failure leaves the DevLoop result unchanged.
- [ ] T8. Tamper evidence: mutating a field of a loaded context and
  recomputing the hash no longer matches `context_id`, and
  `validate()` rejects it.
- [ ] T9. Replay: `tests/test_workflow_replay.py` passes against the existing
  pre-patch histories (`tests/fixtures/histories/dev_loop_full.prepatch.json`)
  with the new `workflow.patched("execution-identity")` marker, plus a new
  patched history recorded via `tools/record_workflow_history.py`.
- [ ] T10. Projection: `to_execution_correlation()` produces a valid
  `context_snapshot.ExecutionCorrelation` that passes
  `ContextSnapshot.validate()` when embedded in a sealed snapshot.

## Rollback

The change is additive and reversible in three independent layers, in this
order:

1. **Runtime surface (instant).** Unset `MCTL_EXECUTION_CONTEXT_FILE` in the
   CWFTs and leave `MCTL_REQUIRE_EXECUTION_CONTEXT` unset: every driver falls
   back to an unverified local context, the MCP headers stop being sent, and
   agents behave exactly as before. No code change, no redeploy of mctl-agents.
2. **Control plane (one deploy).** Revert the `_run_cwft` param additions and
   the mint calls. Because the workflow changes sit behind
   `workflow.patched("execution-identity")`, in-flight loops that already
   recorded the marker keep their recorded command order; only loops started
   after the revert skip minting. Removing the marker entirely is NOT safe for
   running executions — prefer leaving the patched branch in place and making
   the mint a no-op if a faster revert is needed.
3. **Records (no rollback needed).** `execution_context_id`/`trace_id` on the
   ledger row and the `execution:` block in `.status.yaml` are read-only
   annotations; stale values are harmless and nothing branches on them. If
   mctl-api rejects the extra fields, step 2's revert stops them being sent and
   already-written rows can be ignored.

Because no consumer is authorized by this data and no existing field changes
meaning, a rollback at any layer degrades observability only — it cannot
strand a proposal, a PR, or a running DevLoop.
