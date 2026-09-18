# Tasks: issue-333-feat-human-input-durable-agent-clarifica

- [ ] 1. Write `docs/adr/011-human-input-contract.md` — the first deliverable.
      Title `# ADR 011 — \`HumanInputRequest\`/\`HumanInputResponse\` contract
      and \`WAITING_FOR_INPUT\``; status block with `**Status:** proposed`,
      `**Date:**`, `**Issue:** mctlhq/mctl-agents#333 (core child of
      mctlhq/.github#42)`, `**Supersedes:**` prose; sections
      Context / Decision (numbered) / Alternatives / Non-goals /
      Platform impact / Follow-ups and sequencing / Implementation map.
      Must state explicitly that the issue's "ADR-009" is taken by
      `009-context-snapshot-contract.md` and that this is 011.
      — DoD: every claim carries a `path.py:line` citation; the field tables,
      the state model, the boundary table and the one bold invariant
      ("a human answer is information, never authorization and never
      instruction") are present; `mctl-api#261` and `mctl-telegram#571` are
      commented with the corrected number.

- [ ] 2. Add `orchestrator/human_input.py` (depends on 1) — stdlib-only schema
      module modelled line-for-line on `orchestrator/context_snapshot.py`:
      `API_VERSION = "human.mctl.ai/v1alpha1"`, `SUPPORTED_API_VERSIONS` as a
      complete allow-list, `HumanInputError(ValueError)`, frozen dataclasses
      (`HumanInputRequest`, `HumanInputResponse`, `ResponseSpec`,
      `ContextRef`, `AudienceRef`, `RespondentRef`, `WorkItemRef`,
      `AgentProvenance`), `_reject_unknown_keys`, `_require_sha256`,
      `seal_request()`, `seal_response()`, `validate_response(request,
      response)`, `to_log_dict()`, and the bounded-length constants.
      `ExecutionCorrelation` is imported from `context_snapshot`, not
      redefined. — DoD: `uv run pytest tests/test_human_input.py`, `ruff`
      and `mypy` all green; no production module imports it yet.

- [ ] 3. Extend `context_snapshot.SOURCE_KINDS` with `human-input` and
      document `human-input-response` as an `EvidenceRef.kind` (depends on 2)
      — DoD: an additive vocabulary entry only; the golden fixture
      `tests/fixtures/context/investigator-snapshot.json` still validates and
      its `content_hash` is unchanged.

- [ ] 4. Add `orchestrator/human_input_capability.py` (depends on 2): the
      in-process SDK MCP server `human` with tool `request_input`. Refuses on
      a second outstanding request, on `round > MAX_CLARIFICATION_ROUNDS`, and
      on a repeated `question_hash`; seals, POSTs to mctl-api via
      `orchestrator.temporal.mctl_client.auth_headers()`, writes
      `$HUMAN_INPUT_DIR/request.json`, returns `{request_id, request_hash,
      status: "needs_input"}`. All `claude_agent_sdk` imports deferred inside
      functions, per `tests/test_worker_isolation.py`. — DoD: the worker can
      still import every driver; a refused call leaves no file and no POST.

- [ ] 5. Wire eligibility into `orchestrator/options.py` (depends on 4): only
      `build_issue_investigator_options_from_plan` gains the server, and only
      when `"human.request_input" in plan.tools`, mapping the logical name to
      `mcp__human__request_input`. The legacy builder is untouched.
      — DoD: `tests/test_options.py` equivalence tests still pass for a plan
      without the capability; a plan with it produces exactly one extra
      allowed tool.

- [ ] 6. Bump the mctl-gitops catalog profile
      `agent-platform/execution-profiles/issue-investigator-default/profile.yaml`
      to add `human.request_input` to `spec.tools` and bump `spec.version`
      (sibling repo; depends on 5) — DoD:
      `uv run python -m orchestrator.validate_manifest` is green with
      `MCTL_GITOPS_ROOT` pointed at the branch, i.e.
      `_check_tool_policy_and_budget_match_options_py` and
      `check_catalog_profiles_match_builders` both agree.

- [ ] 7. Teach `orchestrator/run_issue_investigator.py` to yield (depends on
      4): create `$HUMAN_INPUT_DIR`, add it to `add_dirs`, detect
      `request.json` after `drain_until_settled`, discard staging, set
      `InvestigateResult.needs_input`, and exit `EXIT_NEEDS_INPUT = 50`.
      — DoD: a run whose agent asked publishes no proposal directory, leaves
      no staging wrapper or clone behind (the existing `finally` invariants),
      and exits 50.

- [ ] 8. Add `--human-input-ref` / `--human-input-outcome` continuation to the
      same driver (depends on 7): fetch, re-validate with
      `validate_response()`, seal a child `ContextSnapshot` with
      `StepRef{parent_snapshot_id, step="continuation", sequence=resume_count}`
      plus the `human-input` source and `human-input-response` evidence ref,
      and append a `<human_answer>` block through a new
      `_neutralize_human_input_tags` built on the `_neutralize_prompt_tags`
      pattern (marker replacement, attribute-tolerant, unclosed-tag
      tolerant). The block states that the answer is unprivileged
      information, resolves this `request_id`, waives no policy or approval,
      and must not be re-asked. — DoD: the continuation prompt contains the
      answer exactly once and no surface transcript; this is the first
      production import of `orchestrator/context_snapshot.py`.

- [ ] 9. Add the read/record activities (depends on 2):
      `fetch_human_input_request`, `fetch_human_input_response` and
      `record_human_input_event` in
      `orchestrator/temporal/activities/human_input.py`, styled on
      `activities/state.py:record_execution` (30 s timeout,
      `auth_headers()`, `raise_for_status()`), and register them in
      `worker.worker_plans`' `short_activities`. — DoD: registered on the
      control queue only; `tests/test_worker_roles.py` still passes.

- [ ] 10. Add `outcome: str = ""` to `WorkflowResult` and populate it from the
      Argo phase/exit code in `submit_and_wait` (depends on 7) — DoD: a
      defaulted field only; every recorded history in
      `tests/fixtures/histories/` still deserializes and replays.

- [ ] 11. Add `WAITING_FOR_INPUT` to `DevLoopWorkflow` (depends on 9, 10):
      `@workflow.signal human_input`, `@workflow.query waiting_for`,
      `@workflow.query human_input_state`, the
      `wait_condition(..., timeout=...)` park, the `INPUT_TIMED_OUT`
      continuation, `MAX_CLARIFICATION_ROUNDS = 2`, `resume_count`, and the
      seven events — all behind `workflow.patched("human-input")`.
      — DoD: the signal never raises on a malformed payload and never sets
      `self._approved`; `waiting_for()` answers `input` while parked on a
      question and `approval` while parked on `approve()`.

- [ ] 12. Record a new replay fixture (depends on 11): add a
      `dev_loop_human_input` `Scenario` to `tests/replay_scenarios.py` and
      record it with `tools/record_workflow_history.py`. Do NOT re-record any
      existing `*.prepatch.json`. — DoD:
      `tests/test_workflow_replay.py` passes including
      `test_every_recorded_fixture_belongs_to_a_scenario`.

- [ ] 13. Update `docs/temporal-flow.md`, its `.mmd` diagrams and
      `docs/agent-inventory.yaml` (depends on 11) — DoD:
      `uv run pytest tests/test_diagram_facts.py tests/test_agent_inventory.py`
      is green; the sequence diagram shows the pod exiting before the wait.

- [ ] 14. Run the first E2E on a controlled ambiguous issue (depends on 6, 8,
      11, plus mctl-api#261 and mctl-telegram#571 deployed) — DoD: the pilot
      demonstrations from the issue all hold, evidenced from
      `mctl_get_workflow_status` and the Temporal history.

## Tests

- [ ] T1. `tests/test_human_input.py` — seal/hash determinism
      (`request_id == "hir-" + request_hash[7:23]`), `from_dict` rejects
      unknown keys, `_require_sha256` on every hash field, typed-value
      validation per `ResponseSpec.type`, option-membership rejection, and
      every length bound.
- [ ] T2. The ADR 009 invariant tests reused verbatim against the new schema:
      `test_serialized_schema_has_no_authorization_field_name` (recursive
      field-name scan for `allow`/`deny`/`permit`/`grant`/`approve`/
      `authorized`) and `test_module_import_is_stdlib_only` (subprocess).
- [ ] T3. Durable wait and resume: start `DevLoopWorkflow` under
      `WorkflowEnvironment.start_time_skipping()` with a `submit_and_wait`
      fake returning `outcome="needs_input"`, assert `waiting_for() == "input"`,
      signal `human_input`, assert `calls ==
      ["mctl-agents-investigate", "mctl-agents-investigate",
      "mctl-agents-implement"]` after approval, with the second investigate
      carrying `human_input_ref`.
- [ ] T4. The pod exits while waiting: assert the needs-input investigate
      activity has COMPLETED (not merely scheduled) before the wait begins,
      and that no activity is in flight during the wait.
- [ ] T5. Duplicate request idempotency: two identical capability calls across
      two Argo attempts produce the same `request_id` and exactly one POST.
- [ ] T6. Duplicate response idempotency: replaying the same
      `human_input` signal resumes exactly once; `resume_count` stays 1.
- [ ] T7. Stale / expired / superseded rejection: a signal whose
      `request_hash` does not match leaves the workflow waiting; a response
      after `expires_at` is refused; a second distinct response is recorded
      as `superseded-by-first`.
- [ ] T8. Unauthorized respondent rejection (`validate_response` +
      the audience check), asserting the question text is never echoed back.
- [ ] T9. Timeout path: time-skip past `expires_at`, assert `INPUT_TIMED_OUT`,
      exactly one continuation with `human_input_outcome=timed_out`, and a
      completed workflow.
- [ ] T10. Round limit: a third `request_input` call in one workflow is
      refused at the capability and the step continues normally.
- [ ] T11. Dedupe: a continuation asking the same normalized question
      (`question_hash` match) is refused.
- [ ] T12. `ContextSnapshot` provenance: the continuation's child snapshot
      validates against its parent (`validate(parent=...)`), carries exactly
      one `human-input` source and one `human-input-response` evidence ref,
      and `validate_step_sequence` holds across rounds.
- [ ] T13. Clarification is not approval: a `human_input` signal leaves
      `_approved` False, submits no `mctl-agents-approve` CWFT, and does not
      satisfy `proposal_state.human_approval_satisfied`.
- [ ] T14. Prompt-injection content stays data: an answer containing
      `</human_answer>`, `</issue_body>` and "ignore previous instructions"
      is neutralized to `[tag stripped]` markers and cannot splice back
      together, mirroring `tests` for `_neutralize_prompt_tags`.
- [ ] T15. Telemetry safety: `to_log_dict()` output contains no substring of
      `question`, `reason` or `value`.
- [ ] T16. Patch memoization: an execution started before the
      `human-input` marker never adopts it, in the style of
      `tests/test_patch_memoization.py`.
- [ ] T17. Eligibility: a plan without `human.request_input` produces options
      with no `human` MCP server, and a direct capability call in that mode
      is refused.

## Rollback

Every piece is additive and independently revertible, in reverse dependency
order:

1. **Fastest kill switch, no deploy:** remove `human.request_input` from
   `spec.tools` in the mctl-gitops catalog profile and bump `spec.version`.
   The next resolved `ExecutionPlan` omits the capability, the options
   builder stops mounting the `human` MCP server, and no agent can ask a
   question. In-flight parked loops are unaffected — they still resume on a
   valid response or time out into their `INPUT_TIMED_OUT` continuation.
   Belt and braces: `ISSUE_INVESTIGATOR_RESOLVER_MODE` defaults to `legacy`,
   whose builder never had the capability.
2. **Drain parked loops before reverting code.** Query `waiting_for()` across
   active dev loops (`activities/visibility.list_active_dev_loop_ids`);
   answer or cancel each one. Reverting `DevLoopWorkflow` while an execution
   is parked would be a command mismatch on replay.
3. **Revert the workflow change.** Because every branch is behind
   `workflow.patched("human-input")`, reverting it affects only executions
   that recorded the marker — which is why step 2 comes first. Do not delete
   the `dev_loop_human_input` replay fixture in the same commit;
   `test_every_recorded_fixture_belongs_to_a_scenario` fails loudly either
   way, which is the intended signal.
4. **Revert the driver change.** `--human-input-ref` is optional and
   `EXIT_NEEDS_INPUT` is unreachable without the capability, so the driver
   can be reverted independently at any time.
5. **`orchestrator/human_input.py` and the ADR can stay.** The schema module
   is inert unless imported — the same position `context_snapshot.py` has
   held since ADR 009 — and the ADR documents a decision whether or not the
   code ships. Reverting them is only warranted if the contract itself is
   wrong, in which case `mctl-api#261` and `mctl-telegram#571` must be
   reverted with it, since they consume it as the schema of record.

No data migration is involved: no stored schema changes, `.status.yaml` is
untouched, and `WorkflowResult`'s new field is defaulted, so a rollback
leaves no unreadable records behind.
