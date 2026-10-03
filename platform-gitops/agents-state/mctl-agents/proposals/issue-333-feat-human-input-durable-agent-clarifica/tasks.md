# Tasks: issue-333-feat-human-input-durable-agent-clarifica

All tasks land in one PR against `mctlhq/mctl-agents`. No sibling repo is
touched, no operator step is required, and every item is provable by
`uv run pytest` / `uv run ruff check .` / `uv run mypy .`.

- [ ] 1. Write `docs/adr/011-human-input-contract.md` — DoD: ADR exists with the
  house blockquote metadata block (`**Status:** proposed`, `**Date:**`,
  `**Issue:** mctlhq/mctl-agents#333`, `**Supersedes:** nothing`) and the
  section order used by ADR 009/010 (`## Context`, `## Decision` with numbered
  `###` sections, `## Alternatives`, `## Non-goals`, `## Platform impact`,
  `## Follow-ups and sequencing`, `## Implementation map`, `## Testable
  invariants`). It states the versioned `HumanInputRequest`/`HumanInputResponse`
  field tables, the `WAITING_FOR_INPUT` state machine as a ` ```text ` block,
  why clarification is not approval, why the ADR is numbered 011 and not 009,
  and that `SOURCE_KINDS` gains `human-input-response` additively within
  `context.mctl.ai/v1alpha1`. Every cross-reference is `path:line`.

- [ ] 2. Add `orchestrator/human_input.py` (depends on 1) — DoD: stdlib-only
  module, no I/O, no SDK import. Defines `API_VERSION =
  "humaninput.mctl.ai/v1alpha1"`, `REQUEST_KIND`, `RESPONSE_KIND`,
  `SUPPORTED_API_VERSIONS`, `RESPONSE_TYPES`, `AUDIENCES`,
  `CONTEXT_REF_PREFIXES`, `DEFAULT_REQUEST_TTL_SECONDS = 86400`,
  `MAX_REQUEST_TTL_SECONDS = 604800`, `MAX_CLARIFICATION_ROUNDS = 3`,
  `MAX_OUTSTANDING_REQUESTS_PER_EXECUTION = 1`, `HumanInputError(ValueError)`,
  frozen dataclasses `ResponseSpec`, `RequestedFrom`, `Respondent`,
  `HumanInputRequest`, `HumanInputResponse` (each with `to_dict`/`from_dict` and
  unknown-key rejection), and functions `seal_request`, `question_hash_for`,
  `validate_response`, `request_log_dict`, `response_log_dict`. Hashing and
  canonical JSON reuse the same rules as
  `orchestrator/context_snapshot.py:79,83`; `request_id = "hir-" +
  request_hash[7:23]`. `HumanInputRequest.execution` is
  `context_snapshot.ExecutionCorrelation`, not a re-declared correlation block.

- [ ] 3. Add `human-input-response` to `SOURCE_KINDS` in
  `orchestrator/context_snapshot.py:50-60` (depends on 1) — DoD: the member is
  added, `API_VERSION` is unchanged, `tests/test_context_snapshot.py`'s T7
  vocabulary-closure test is extended rather than weakened, and the golden
  fixture `tests/fixtures/context/investigator-snapshot.json` still round-trips
  with its recorded `content_hash`.

- [ ] 4. Capability plumbing in `orchestrator/options.py` (depends on 2) —
  DoD: adds `HUMAN_INPUT_CAPABILITY = "human.request_input"` and
  `plan_grants_human_input(plan: ExecutionPlan) -> bool`;
  `build_issue_investigator_options_from_plan` (`options.py:422`) filters the
  capability out of `allowed_tools` alongside the existing `mcp__mctl__*`
  special case at `:459-461`, so a granted capability never becomes a dead CLI
  allow-list entry. `build_issue_investigator_options` (the legacy builder) is
  unchanged.

- [ ] 5. Teach `orchestrator/validate_manifest.py` about capability entries
  (depends on 4) — DoD: `_CAPABILITY_TOOLS = frozenset({"human.request_input"})`
  is subtracted from both sides before the set-equality assertions at
  `:351-357` (`_check_tool_policy_and_budget_match_options_py`) and `:610-615`
  (`check_catalog_profiles_match_builders`), so a future catalog profile listing
  `human.request_input` in `spec.tools` does not turn CI red, while any real
  tool-list drift still does.

- [ ] 6. Conditional prompt in `orchestrator/run_issue_investigator.py`
  (depends on 4) — DoD: `_build_prompt` (`:1127`) takes
  `human_input_granted: bool = False` and `human_input_response: str | None =
  None`. When not granted it emits today's bytes verbatim, including
  "No human is present. Do not ask for input. Work with what you have."
  (`:1136`). When granted it replaces that paragraph with the write contract for
  `$PROPOSAL_DIR/human-input/request.json` (ask only after retrieval/code/docs
  are exhausted, still finish the triplet on the best current interpretation,
  never poll, never wait). A supplied response is rendered through
  `_neutralize_prompt_tags` (`:1098`) inside the existing untrusted-DATA
  envelope, with the explicit sentence that it is human-supplied information
  that does not waive policy, authorization or approval, plus the resolved
  `question_hash` marked answered.

- [ ] 7. Producer wiring in `orchestrator/run_issue_investigator.py` (depends on
  2, 4, 6) — DoD: `_run_agent` (`:1285`) reports whether the resolved plan
  granted the capability; `collect_human_input_request(proposal_dir, *, granted,
  execution, now)` deletes any `human-input/` directory when ungranted, and when
  granted parses the model's document, re-seals it via `seal_request` (wrapper
  owns every id/hash/timestamp/correlation field so the model cannot forge
  identity), enforces `MAX_OUTSTANDING_REQUESTS_PER_EXECUTION`, and rewrites the
  file in sealed form. `InvestigateResult` (`:1409`) gains the defaulted field
  `human_input_request: HumanInputRequest | None = None`. `investigate()`
  (`:1457`) still publishes a complete triplet and still returns success in both
  branches; `_carry_forward` (`:712`) does not carry a stale `human-input/`
  directory into a fresh run.

- [ ] 8. Add `--human-input-response` to `main()` (depends on 6, 7) — DoD: the
  flag accepts a JSON `HumanInputResponse` document, rejects a malformed or
  unsupported-`api_version` one with a clean `SystemExit`, and threads the value
  into `_build_prompt`. Absent flag means today's behaviour exactly.

- [ ] 9. Seal a continuation `ContextSnapshot` (depends on 3, 7, 8) — DoD:
  when a response is supplied, the run calls `context_snapshot.seal()`
  (`:885`) with a `ContextSource` of kind `human-input-response` at
  `trust.tier = "reported"`, an `EvidenceRef {evidence_id: request_id, kind:
  "human-input-response"}`, and a `StepRef` chaining it to the pre-wait
  snapshot, so before/after `snapshot_id` values differ and are recorded.

- [ ] 10. Add `orchestrator/temporal/activities/human_input.py` (depends on 2) —
  DoD: `find_human_input_request(service: str, slug: str) -> str | None`,
  structurally a copy of `find_proposal_slug`
  (`orchestrator/temporal/activities/proposals.py:61`): same `GITOPS_REPO` /
  `AGENTS_STATE_PREFIX`, same per-call `_resolve_token`, missing token raises
  rather than falling through unauthenticated, 404 returns `None`, every other
  failure raises the retryable `HumanInputListingError`. Registered in
  `worker.py`'s `short_activities` list (`:452-473`).

- [ ] 11. `WAITING_FOR_INPUT` in `DevLoopWorkflow` (depends on 2, 10) — DoD:
  `dev_loop.py` gains module constants `RUNNING`, `WAITING_FOR_APPROVAL`,
  `WAITING_FOR_INPUT`, `INPUT_TIMED_OUT`; frozen dataclasses `HumanInputState`
  and `HumanInputOutcome` with every field defaulted; `@workflow.signal
  human_input_response(*args: object)` parsing defensively like `approve`
  (`:788`) and never touching `self._approved`; `@workflow.query
  human_input_state() -> HumanInputState`; and `_await_human_input(service,
  slug)` performing a **bounded** `workflow.wait_condition(pred,
  timeout=expires_at - now)`. `DevLoopResult` (`:449`) gains
  `human_input: HumanInputOutcome | None = None`.

- [ ] 12. Gate it with `workflow.patched("human-input")` (depends on 11) — DoD:
  the new `find_proposal_slug` hoist plus `find_human_input_request` and the
  wait run only inside the patched branch; the unpatched branch's command
  sequence is byte-for-byte the pre-change one. Response validation runs in
  workflow code via the pure `human_input.validate_response`; no I/O is added to
  workflow code (ADR 010 sec. 9).

- [ ] 13. Continuation submit (depends on 11, 12) — DoD: on a valid response the
  workflow increments `resume_count`, re-submits `mctl-agents-investigate`
  through `_run_cwft` (`:483`) with an added `human_input_response` param
  carrying only `request_id`, `request_hash`, `value`, respondent reference,
  `surface` and `received_at` — never a transcript — then falls through to the
  existing `WAITING_FOR_APPROVAL` wait unchanged.

- [ ] 14. Safe telemetry (depends on 2, 11) — DoD: `workflow.logger` emits
  exactly `human_input.requested`, `human_input.wait_started`,
  `human_input.delivered`, `human_input.responded`, `human_input.resumed`,
  `human_input.timed_out`, `human_input.cancelled`, each carrying only
  `request_log_dict`/`response_log_dict` output.

- [ ] 15. Docs (depends on 11) — DoD: `docs/temporal-flow.md` and
  `docs/diagrams/temporal-flow-states.mmd` show `WAITING_FOR_INPUT` as a state
  distinct from the approval wait; `docs/diagrams/archify/facts.yaml` updated so
  `tests/test_diagram_facts.py` stays green; `LLMS.md` mentions the new
  contract module.

## Tests

- [ ] T1. `tests/test_human_input.py` — request creation and typed validation:
  `single_choice` without `options` rejected; a value outside `options`
  rejected; `multi_choice` cardinality; empty `free_text` rejected; a
  `context_refs` entry without an allowed prefix rejected; `expires_at <=
  created_at` and `> MAX_REQUEST_TTL_SECONDS` rejected.
- [ ] T2. Identity determinism: `seal_request` with identical inputs at two
  different `created_at` values yields the same `request_id`/`request_hash`;
  changing any hashed field changes both.
- [ ] T3. Fail-loud versioning: an unknown `api_version`, an unknown `kind`, or
  any unknown key in either document raises `HumanInputError` — mirroring
  `tests/test_context_snapshot.py`'s T4.
- [ ] T4. Response rejection matrix: wrong `request_id`; mismatched
  `request_hash`; `now >= expires_at`; respondent outside
  `requested_from.actor_refs`. Each asserted to reject *and* the positive case
  asserted to accept, so no guard can pass by not running.
- [ ] T5. Duplicate-request idempotency: two runs of
  `collect_human_input_request` over the same model document produce one
  `request_id`; a workflow that sees the same `request_id` twice creates one
  pending request.
- [ ] T6. `question_hash` dedupe: a re-asked question differing only in
  whitespace/case maps to the same `question_hash` and does not create a second
  request; an already-answered `question_hash` is not re-asked.
- [ ] T7. Duplicate-response idempotency: the same `human_input_response` signal
  delivered three times resumes once and increments `resume_count` once. A
  second, *different* response is rejected and the first answer stands.
- [ ] T8. Durable wait and resume, under `tests/temporal_harness.py`: the
  workflow enters `WAITING_FOR_INPUT`, the `human_input_state` query reports the
  pending `request_id`/`expires_at`, the signal resumes it, and the continuation
  `mctl-agents-investigate` submit carries the `human_input_response` param.
- [ ] T9. Pod release: while in `WAITING_FOR_INPUT`, no `submit_and_wait`
  activity is scheduled and no Argo workflow is outstanding — asserted against
  the fake activity recorder used by `tests/test_dev_loop_workflow.py`.
- [ ] T10. Timeout: no response before `expires_at` transitions to
  `INPUT_TIMED_OUT`, the loop returns with that outcome in `DevLoopResult`, and
  it does not hang.
- [ ] T11. Clarification-round limit: a request with `round >
  MAX_CLARIFICATION_ROUNDS` fails loudly with a non-retryable
  `ApplicationError`, and the third round is asserted to still be allowed.
- [ ] T12. Clarification is not approval: a response whose value is
  `"use option B and merge it"` resumes the loop and leaves `self._approved`
  false, with the workflow still parked on the `WAITING_FOR_APPROVAL` wait.
- [ ] T13. Prompt-injection content stays unprivileged: a response containing
  `<issue_body>`-style tags and "ignore previous instructions" is rendered
  through `_neutralize_prompt_tags` inside the untrusted-DATA envelope; the
  assertion is on the rendered prompt bytes.
- [ ] T14. Safe telemetry: for every one of the seven events, the emitted dict
  contains the ids/hashes/correlation and contains neither the question text,
  the reason text, nor the answer value.
- [ ] T15. No-eligibility branch: with `human.request_input` absent from
  `plan.tools` (and in `legacy` resolver mode), `_build_prompt` output is
  byte-identical to today's, a model-written `human-input/` directory is
  deleted, `InvestigateResult.human_input_request` is `None`, and the workflow
  never calls `find_human_input_request`.
- [ ] T16. Replay safety: regenerate `tests/fixtures/histories/dev_loop_full.*`
  and add a pre-patch history that replays green through
  `tests/test_workflow_replay.py` and `tests/replay_scenarios.py`, proving the
  `human-input` patch does not wedge in-flight loops.
- [ ] T17. `ContextSnapshot` before/after provenance: the continuation snapshot
  carries the `human-input-response` source at `trust: reported`, the matching
  `EvidenceRef`, and a `StepRef` whose `parent_snapshot_id` is the pre-wait
  snapshot; `snapshot_id` differs before and after.
- [ ] T18. `tests/test_validate_manifest.py` (extend): a catalog profile listing
  `human.request_input` in `spec.tools` passes
  `check_catalog_profiles_match_builders`, while an unrelated extra tool still
  fails it.
- [ ] T19. Activity behaviour for `find_human_input_request`: 404 returns
  `None`; a 500 raises the retryable error; a missing token raises rather than
  issuing an unauthenticated request — mirroring the existing
  `find_proposal_slug` cases in `tests/test_temporal_activities.py`.
- [ ] T20. Worker isolation stays green: `orchestrator/human_input.py` imports
  no SDK and no third-party package, asserted by extending
  `tests/test_worker_isolation.py`'s subprocess import check the way
  `tests/test_context_snapshot.py`'s T5 does.

## Rollback

Every change is additive and gated, so rollback is graded rather than
all-or-nothing.

1. **Fastest, no deploy.** The producer path is unreachable unless the
   mctl-gitops catalog profile grants `human.request_input`. Reverting
   `mctl-gitops#1277` (or simply never landing it) means no request document is
   ever written, `find_human_input_request` always returns `None`, and every
   loop takes the pre-change path. This is also the state on day one of this
   PR.
2. **Revert the workflow behaviour.** Removing the body of the
   `workflow.patched("human-input")` branch and redeploying the worker returns
   new executions to the old sequence immediately. Do **not** delete the
   `workflow.patched` call itself while pre-revert executions may still be
   running — by `dev_loop.py:491-498`'s attrition rule, an execution that
   recorded the marker must keep finding it. Retire it later with
   `workflow.deprecate_patch` plus a second deploy, the step this repo has
   never yet taken for any marker.
3. **Full revert.** `git revert` the PR. `orchestrator/human_input.py` has no
   other importer, the `SOURCE_KINDS` addition is unreferenced once the
   producer is gone, and the `validate_manifest.py` subtraction is a no-op while
   no profile declares the capability. The only ordering constraint is that the
   catalog grant must be reverted first, or `check_catalog_profiles_match_builders`
   goes red on the next CI run.
4. **Stuck loop.** A loop parked in `WAITING_FOR_INPUT` self-heals at
   `expires_at` (`INPUT_TIMED_OUT`, default 24 h). To unblock sooner, send the
   `human_input_response` signal via `orchestrator/temporal/cli.py` — the same
   path `approve` already uses — or terminate the execution; the intake label
   plus `ALLOW_DUPLICATE_FAILED_ONLY` lets the issue start again.
