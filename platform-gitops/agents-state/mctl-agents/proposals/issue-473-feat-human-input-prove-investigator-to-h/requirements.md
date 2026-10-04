# Prove investigator to human to automatic continuation (human-input devloop-e2e)

## Context

Issue mctlhq/mctl-agents#473 binds the `devloop-e2e` work item (phase `e2e`) of the
"Durable agent clarification / feedback primitive" epic (mctlhq/.github#42,
`roadmap/epics/human-input.yaml`). The epic's goal is an agent that can suspend durable
work, ask an authorized human for missing information, and resume the same WorkItem
without treating clarification as approval. The work item asks for proof that the whole
path works end to end: the investigator asks, a human answers, and the loop continues
on its own.

Most of the consumer half is already in place. `orchestrator/human_input.py` defines the
sealed `HumanInputRequest` and `HumanInputResponse` contract (ADR 013). `DevLoopWorkflow`
(`orchestrator/temporal/workflows/dev_loop.py`) reads `human-input/request.json` back
through `find_human_input_request`, parks in `WAITING_FOR_INPUT`, validates a
`human_input_response` signal, and resubmits `mctl-agents-investigate` with a
`human_input_responses` JSON array. The producer half does not exist yet. Today
`orchestrator/run_issue_investigator.py` never seals a request, never writes
`request.json`, and has no `--human-input-responses` argument. ADR 013 and the
activity docstring both say so. Because of that, the existing tests
(`TestDevLoopHumanInput` in `tests/test_dev_loop_workflow.py`) only prove the workflow
against hand-sealed fixtures. This proposal adds the minimal producer and consumer
pieces to the investigator, plus an automated end-to-end acceptance test that chains
them through the real `DevLoopWorkflow`. It also adds an operator runbook for the live
proof.

## User stories

- AS an issue-investigator run that cannot resolve an ambiguity, I WANT to emit one
  structured question instead of guessing, SO THAT the proposal is grounded in the
  human's actual intent.
- AS the work-item owner, I WANT to answer that question once through an authorized
  surface (for example Telegram), SO THAT the investigation continues without me
  re-triggering anything.
- AS a platform operator, I WANT a repeatable automated test and a short live runbook
  that prove investigator -> human -> automatic continuation, SO THAT the `devloop-e2e`
  work item can be closed as completed with evidence.
- AS a reviewer of the approval gate, I WANT proof that a clarification answer never
  flips approval, SO THAT the human approval gate stays the only path to implementation.

## Acceptance criteria (EARS)

- WHEN the resolved `ExecutionPlan` grants `human.request_input`
  (`orchestrator.options.plan_grants_human_input`) THE SYSTEM SHALL add a prompt section
  to the investigator prompt (`_build_prompt`). The section tells the model how to
  request clarification: write `$PROPOSAL_DIR/human-input/draft.json` containing
  `question`, `reason` and a `response` spec.
- WHILE the plan does not grant `human.request_input` THE SYSTEM SHALL leave the prompt
  byte-identical to today's prompt.
- WHEN the agent run ends and a valid `human-input/draft.json` exists, the capability is
  granted, and both `--temporal-workflow-id` and `--temporal-run-id` were passed, THE
  SYSTEM SHALL build the request with `orchestrator.human_input.seal_request`. It SHALL
  write the result as `human-input/request.json` in the published proposal directory and
  remove `draft.json` before publishing.
- WHEN sealing a request THE SYSTEM SHALL fill in every field the orchestrator owns
  itself, never from model output: `work_item_id`, `execution` (the
  `ExecutionCorrelation` with the loop's workflow id and run id),
  `requested_from.audience = "work_item_owner"`, `actor_refs` naming the issue author,
  `created_at`, `expires_at = created_at + DEFAULT_REQUEST_TTL_SECONDS`, and
  `round = (number of accepted responses received) + 1`.
- IF `draft.json` is malformed, exceeds the size cap, is not granted, or lacks loop
  identity THEN THE SYSTEM SHALL discard it and publish the proposal as usual. It SHALL
  not write `request.json`, and it SHALL record the typed `outcome_reason` slug
  `human-input-draft-rejected` on the `InvestigateResult`.
- WHEN the investigator is invoked with `--human-input-responses <json>` THE SYSTEM SHALL
  validate every entry: exactly the keys `request_id`, `request_hash`, `value`,
  `respondent`, `surface` and `received_at`, with `request_id` matching `hir-` and
  `request_hash` matching `sha256:`. It SHALL then render the answers into the prompt
  inside an untrusted-data block that `_neutralize_prompt_tags` has passed over, and it
  SHALL state in the prompt that the listed questions are resolved.
- IF `--human-input-responses` is not valid JSON or any entry fails validation THEN THE
  SYSTEM SHALL exit non-zero before any model call.
- WHEN a continuation run publishes without a new draft THE SYSTEM SHALL not carry the
  previously answered `human-input/request.json` forward into the new proposal
  directory. In its place it SHALL write `human-input/answered.json`, which lists only
  the `request_id`, `request_hash` and `received_at` of each answered request.
- WHILE writing `request.json` or `answered.json`, or logging about them, THE SYSTEM
  SHALL never log `question`, `reason` or `value`. Logs carry ids, hashes, rounds and
  counters only (ADR 013 "No transcripts").
- WHEN the automated end-to-end test runs THE SYSTEM SHALL prove this sequence in order,
  within a single `DevLoopWorkflow` execution:
  (a) The first investigate produces a request through the real producer code path.
  (b) The workflow reaches `WAITING_FOR_INPUT` for that `request_id`.
  (c) A valid `human_input_response` signal resumes it with no other operator action.
  (d) The continuation investigate receives `human_input_responses` containing that
  `request_id` and `request_hash`.
  (e) The continuation's prompt renders the answer.
  (f) The loop then waits in `WAITING_FOR_APPROVAL` and has not run the implementer.
- WHILE a clarification answer is being processed THE SYSTEM SHALL leave `_approved`
  untouched. The end-to-end test SHALL assert that the implementer has not run before
  the explicit `approve` signal.

## Out of scope

- The Telegram adapter that turns a chat reply into a `human_input_response` signal
  (mctlhq/mctl-telegram#571). The automated test signals the workflow directly.
- Declaring `human_input_responses` on the `mctl-agents-investigate` CWFT in mctl-gitops,
  and on the mctl-api parameter allow-list (mctl-api#372 strips undeclared parameters).
  These are cross-repo prerequisites for the live proof only. The runbook names them.
- Granting `human.request_input` in the `issue-investigator-default` ExecutionProfile
  (`catalog-profile-rollout`, mctlhq/mctl-gitops#1277, already closed).
- Changes to `DevLoopWorkflow` wait semantics, `MAX_CLARIFICATION_ROUNDS` or the
  `orchestrator/human_input.py` schema.
- Clarification for any agent other than issue-investigator.

## Open questions

- Is `human_input_responses` already declared on the investigate CWFT and in mctl-api?
  The workflow comment at `dev_loop.py` around line 2979 says pinning it is "producer-side
  work (#451)". If it is not declared, the live proof is blocked on that, but the
  automated proof in this proposal is not.
- Does mctlhq/mctl-agents#451 (the producer and answered-marker tracker) overlap with
  this work? This proposal assumes #473 delivers the minimal producer that #451
  describes. If #451 is implemented separately first, tasks 1-4 shrink to verification.
- Should the answer `value` itself be persisted in gitops (`answered.json`)? This
  proposal persists only ids, hashes and timestamps. The value travels to the
  continuation through the CWFT parameter, in line with ADR 013 "No transcripts".
- Who is the authorized respondent: the issue author, or the configured repo operators?
  This proposal uses the issue author (`audience=work_item_owner`). To do that it adds
  `author` to the `gh issue view --json` fields.
- What closes the epic item: the automated test alone, or also one recorded live run?
  This proposal delivers both and leaves the live run as a runbook step that runs once
  the cross-repo prerequisites land.
