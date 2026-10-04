# Tasks: issue-473-feat-human-input-prove-investigator-to-h

- [ ] 1. Add `author` to the `gh_issue_view` JSON field list and an `author: str = ""`
  field to `IssueData` in `orchestrator/run_issue_investigator.py`. Update the fixtures
  in `tests/test_run_issue_investigator.py`. — DoD: `IssueData.author` is populated from
  `data["author"]["login"]`, and existing tests pass unchanged apart from the fixture
  addition.
- [ ] 2. Add `--human-input-responses` to argparse and `_parse_human_input_responses(raw)`,
  and thread `human_input_responses` through `investigate` -> `_investigate` ->
  `_build_prompt`. — DoD: valid arrays parse to a list of dicts. Invalid JSON, unknown
  keys, bad `hir-` or `sha256:` prefixes, a non-ISO `received_at`, or more than
  `MAX_CLARIFICATION_ROUNDS` entries each raise `SystemExit` before any clone or model
  call.
- [ ] 3. Add `_human_input_prompt_block(granted, answers)` and call it from
  `_build_prompt`. Answers are rendered inside `<human_answers>` after
  `_neutralize_prompt_tags`. (depends on 2) — DoD: the prompt is byte-identical when the
  capability is not granted and no answers exist. When granted, the block describes
  `human-input/draft.json`. When answers exist, the block lists them as resolved.
- [ ] 4. Hoist `context_assembly.build_execution_correlation` in `_run_agent` so that it
  also runs for a declarative plan with `plan_grants_human_input(plan)`, and return the
  correlation to `_investigate`. — DoD: the options built are unchanged (the
  `tests/test_options.py` equivalence tests pass), and the correlation carries the
  `temporal_workflow_id` and `temporal_run_id` that were passed.
- [ ] 5. Add `_seal_draft(...)`, which reads `human-input/draft.json` (no-follow,
  regular file, 16 KiB cap), builds the `ResponseSpec`, calls
  `human_input.seal_request` with orchestrator-owned identity, TTL, round and requested
  respondent, writes `human-input/request.json` and deletes the draft. Call it in
  `_investigate` before publication. (depends on 1, 4) — DoD: a valid draft produces a
  `request.json` that `HumanInputRequest.from_dict(...).validate()` accepts. Each
  rejection case removes the draft, writes no request, publishes the triplet, and sets
  `outcome_reason="human-input-draft-rejected"`. The rejection cases are: a malformed
  draft, an oversize draft, no grant, legacy mode, missing loop ids, an empty author,
  and the round limit reached. Logs contain only `request_log_dict` fields.
- [ ] 6. On a continuation run, exclude an answered `human-input/request.json` from
  `_carry_forward`, and write `human-input/answered.json` containing
  `[{request_id, request_hash, received_at}]` when no new request was sealed.
  (depends on 2, 5) — DoD: the published directory never contains a `request.json`
  whose `request_id` is among the supplied answers, and `answered.json` holds no
  `value`.
- [ ] 7. Add the end-to-end test `tests/test_human_input_e2e.py`. If importing from a
  test module is not allowed, first move `_fake_activities` and
  `_wait_for_pending_request` into `tests/temporal_harness.py`. (depends on 3, 5, 6) —
  DoD: a single `DevLoopWorkflow` execution proves the full sequence: request produced
  by the real producer, then `WAITING_FOR_INPUT`, then the signal, then a continuation
  investigate that carries `human_input_responses` with the sealed id and hash, then the
  prompt renders the answer, then the approval park with the implementer not yet run,
  then `approve`, then the implementer runs. The test passes under `uv run pytest`.
- [ ] 8. Add the live runbook `docs/runbooks/human-input-e2e.md`. Update ADR 013's
  Producer line and the module docstring in
  `orchestrator/temporal/activities/human_input.py`. (depends on 5) — DoD: the runbook
  lists the cross-repo prerequisites (CWFT parameter, mctl-api allow-list, profile
  grant, mctl-telegram#571), the trigger, the observe and answer steps, the
  verification checks, and an evidence template for #473. No doc still says the
  producer "does not exist yet".
- [ ] 9. Run `uv run ruff check` and the full test suite, then open the PR referencing
  #473 and #451. (depends on 1-8) — DoD: CI is green.

## Tests

- [ ] T1. `_parse_human_input_responses`: covers valid input, plus every rejection
  class (bad JSON, non-list, unknown key, missing key, bad prefix, bad timestamp, too
  many entries).
- [ ] T2. `_human_input_prompt_block`: the output is empty when the capability is not
  granted and no answers exist. The `_build_prompt` output is byte-identical to the
  pre-change golden for the ungranted case. A `</human_answers>` injection inside a
  `value` is neutralized.
- [ ] T3. `_seal_draft` happy path: the sealed request round-trips through `from_dict`.
  `execution.temporal_workflow_id` and `temporal_run_id` match the inputs, `actor_refs`
  is `("github:<author>",)`, `round` is answers + 1, and `expires_at - created_at` is
  `DEFAULT_REQUEST_TTL_SECONDS`.
- [ ] T4. `_seal_draft` rejections: one case each for malformed, oversize, symlinked
  draft, ungranted, legacy mode, missing run id, empty author, and round limit. For
  every case, assert that no `request.json` exists, the draft is removed, and the
  outcome reason is set.
- [ ] T5. A model-supplied `execution`, `requested_from` or `expires_at` key in
  `draft.json` is rejected rather than honoured.
- [ ] T6. The continuation carry-forward drops the answered `request.json` and writes
  an `answered.json` that contains no `value`.
- [ ] T7. Log hygiene: run `caplog` over T3 and T6 and assert that the question,
  reason, and value strings never appear.
- [ ] T8. End to end (task 7): investigator, then human, then automatic continuation,
  then approval gate, inside one `DevLoopWorkflow` execution. A second case checks that
  a continuation which seals a round-2 request parks again, and that the third answer
  hits `MAX_CLARIFICATION_ROUNDS`.
- [ ] T9. The existing `tests/test_dev_loop_workflow.py::TestDevLoopHumanInput`,
  `tests/test_human_input.py`, `tests/test_options.py`, `tests/test_manifest.py` and
  `tests/test_workflow_replay.py` all pass unchanged.

## Rollback

Every change is in the investigator process and in tests or docs. None of it touches
the Temporal workflow code, so rolling back carries no replay hazard. To roll back,
revert the PR and redeploy the investigator image through the normal release, or pin
the previous `issue-investigator` version with `mctl_rollback_agent` or
`mctl_rollback_agent_binding`.

For an immediate kill switch without a code revert, remove `human.request_input` from
the `issue-investigator-default` ExecutionProfile in mctl-gitops. `plan_grants_human_input`
then returns False, the prompt reverts to today's text, and no draft is ever sealed.

Any `human-input/request.json` already published either expires within
`DEFAULT_REQUEST_TTL_SECONDS` or is skipped by the workflow as a foreign or stale
leftover. A parked loop can be ended with the existing abandon path.
