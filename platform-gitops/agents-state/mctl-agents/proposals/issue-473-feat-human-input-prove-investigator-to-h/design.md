# Design: issue-473-feat-human-input-prove-investigator-to-h

## Current state

**Contract.** `orchestrator/human_input.py` is the stdlib-only contract (ADR 013,
`docs/adr/013-human-input-contract.md`). It provides:
- `seal_request(...)`, the only constructor of a sealed `HumanInputRequest`. It derives
  `request_hash`, `request_id = "hir-" + hash[7:23]` and `question_hash`.
- `ResponseSpec`, `RequestedFrom`, `Respondent` and `validate_response`.
- `request_log_dict` and `response_log_dict`, the transcript-free log projections.
- Constants: `DEFAULT_REQUEST_TTL_SECONDS = 86400`, `MAX_REQUEST_TTL_SECONDS = 604800`
  and `MAX_CLARIFICATION_ROUNDS = 3`.

**Consumer (built).**
- `orchestrator/temporal/activities/human_input.py:find_human_input_request(service, slug)`
  reads
  `platform-gitops/agents-state/<service>/proposals/<slug>/human-input/request.json`
  from mctl-gitops main through the contents API.
- In `DevLoopWorkflow.run`, the branch behind `workflow.patched("human-input")` works
  like this:
  - It resolves the slug with `find_proposal_slug`, then calls `_await_human_input`.
  - `_await_human_input` skips the request when its `question_hash` was already
    resolved, when it was sealed by another workflow or run, or when it is stale or
    expired.
  - It enforces `_human_input_resume_count < MAX_CLARIFICATION_ROUNDS` and parks with
    `HumanInputState.state == WAITING_FOR_INPUT`.
  - It validates queued `human_input_response` signals and returns a
    `HumanInputOutcome`.
  - On `answered`, the loop appends to `accepted_answers` and resubmits
    `mctl-agents-investigate` with
    `continuation_params["human_input_responses"] = json.dumps(accepted_answers)`.
    This happens around `dev_loop.py:2960-3015`. The loop then reads the request again,
    and only after that does it fall through to the approval wait.
- The investigate params already carry `temporal_workflow_id` and `temporal_run_id`
  (#461 and #451). This lets a producer stamp the loop identity that
  `_await_human_input` checks.

**Capability.** `orchestrator/options.py` defines
`HUMAN_INPUT_CAPABILITY = "human.request_input"` and `plan_grants_human_input(plan)`.
`orchestrator/validate_manifest.py:_CAPABILITY_TOOLS` subtracts it from the SDK tool
set. It is a grant flag, not a tool the model can call.

**Producer (missing).** `orchestrator/run_issue_investigator.py` (3873 lines) has
these relevant pieces:
- `_build_prompt` (around line 1525) and `_neutralize_prompt_tags`.
- `_run_agent(..., temporal_workflow_id, temporal_run_id)`. It builds an
  `ExecutionCorrelation` through `context_assembly.build_execution_correlation` in
  declarative mode.
- `_investigate(...)`, with staging, `_carry_forward(live, staging)`,
  `_landed_triplet_defects` and the `_OVERWRITABLE_STATUSES = {"proposed"}` rewrite
  rule.
- `InvestigateResult`, with typed `outcome_code` and `outcome_reason`.
- The argparse surface in `main` (around lines 3667-3800). It has `--temporal-*`,
  `--work-item-id` and others, but no `--human-input-responses`.

No code in `orchestrator/` outside `temporal/` imports `human_input` or calls
`seal_request`. `gh_issue_view` fetches `number,title,body,state,url,comments` and does
not include the issue author.

**Tests.** `tests/test_dev_loop_workflow.py::TestDevLoopHumanInput` drives the real
workflow on the Temporal test env. It feeds request JSON hand-sealed with `_sealed_request`
through a fake `find_human_input_request` (the `_fake_activities(human_input_requests=...)`
hook) and signals `_response_payload`. `tests/test_human_input.py` covers the contract.
Nothing exercises a request produced by the investigator, or the investigator's handling
of a continuation.

## Proposed solution

The proposal makes three additive changes in `mctl-agents`. All three are gated so that
behaviour is unchanged wherever the capability is not granted.

### 1. Producer: draft -> sealed request (`run_issue_investigator.py`)

- **Prompt.** Add `_human_input_prompt_block(granted: bool, answers: list[dict]) -> str`
  and call it from `_build_prompt`. The block depends on two conditions:
  - When the capability is granted and fewer than `MAX_CLARIFICATION_ROUNDS` answers
    exist, the block adds instructions. The model may write
    `$PROPOSAL_DIR/human-input/draft.json` as
    `{"question": str, "reason": str, "response": {"type": ..., "choices": [...]?}}`
    only when the issue is genuinely blocked. It must still write the triplet, recording
    the blocker under Open questions.
  - When answers are present, the block renders them inside `<human_answers>` tags as
    untrusted data, after `_neutralize_prompt_tags`. It says that these questions are
    resolved and must not be asked again.

  When the capability is not granted and no answers exist, the block is the empty
  string, so the prompt is unchanged.

  The triplet is still required so the existing publish invariants
  (`_landed_triplet_defects`, `.status.yaml` = `proposed`) stay exactly as they are. The
  draft triplet is overwritable on continuation because `proposed` is in
  `_OVERWRITABLE_STATUSES`.
- **Sealing.** Add `_seal_draft(proposal_dir, *, granted, correlation, work_item_id,
  issue_author, prior_answers, now) -> HumanInputRequest | None`. Call it in
  `_investigate` after the agent returns and before staging is published. It reads
  `human-input/draft.json` with the same no-follow, regular-file discipline used
  elsewhere in the file, and caps the file at 16 KiB. It then builds a
  `ResponseSpec.from_dict`.

  It calls `human_input.seal_request` with orchestrator-owned values only:
  - `work_item_id`: the `--work-item-id` value, or `_canonical_issue_key(issue_url)` if
    absent.
  - `execution`: the same `ExecutionCorrelation` `_run_agent` built, which carries
    `temporal_workflow_id` and `temporal_run_id`.
  - `requested_from`: `RequestedFrom(audience="work_item_owner",
    actor_refs=(f"github:{issue_author}",))`.
  - `created_at`: now.
  - `expires_at`: now + `DEFAULT_REQUEST_TTL_SECONDS`.
  - `round`: `len(prior_answers) + 1`.
  - `context_refs`: `(f"github:{issue_url}",)`.

  It writes `human-input/request.json` as `json.dumps(request.to_dict(), sort_keys=True)`
  and deletes `draft.json`. Any failure produces `None`, deletes the draft, and sets
  `outcome_reason="human-input-draft-rejected"`; the proposal still publishes. The
  failure cases are: a `HumanInputError`, the capability not granted, missing loop ids,
  legacy resolver mode (no plan), or the round limit reached. Only `request_log_dict`
  is logged.
- **Correlation plumbing.** `_run_agent` builds the correlation only in discovery mode
  today. Hoist the `build_execution_correlation` call so that it also runs whenever the
  plan is declarative and the capability is granted, and return it alongside the
  options. This makes no change to which options are built.
- **Issue author.** Add `author` to the `gh issue view --json` field list and an
  `author: str = ""` field to `IssueData`. An empty author means no respondent can be
  named, so sealing is refused fail-closed.

### 2. Continuation: `--human-input-responses`

- Add the argparse option `--human-input-responses` (default `None`), and add a
  `human_input_responses` keyword argument threaded through `investigate` ->
  `_investigate` -> `_build_prompt` and `_seal_draft`.
- Add `_parse_human_input_responses(raw) -> list[dict]`. It requires a JSON list of at
  most `MAX_CLARIFICATION_ROUNDS` objects. Each object must have exactly these keys:
  `request_id`, `request_hash`, `value`, `respondent` and `surface` (strings, with
  prefix checks on the two ids), and `received_at` (ISO-8601). The `value` may be a
  string, a list of strings, or an object, matching `RESPONSE_TYPES`. Any violation
  raises `SystemExit` in `_work_context_from_args`-style validation, before the clone
  or the model call.
- **Answered marker.** On a continuation run, `_carry_forward` skips
  `human-input/request.json` when its `request_id` is in the answers. Unless the model
  sealed a new request, the orchestrator writes `human-input/answered.json` containing
  `[{request_id, request_hash, received_at}]`. The consumer does not depend on this
  file: `_await_human_input` already skips a resolved `question_hash`. The marker exists
  so that a later execution, and a human reading gitops, can see that the question was
  answered, which is the "durable answered-marker" ADR 013 defers to #451.

### 3. End-to-end proof

- **Automated test.** Add `tests/test_human_input_e2e.py`, reusing the harness from
  `tests/test_dev_loop_workflow.py`: `_fake_activities`, `TASK_QUEUE`, the `env` fixture
  and `_wait_for_pending_request`, imported or moved to `tests/temporal_harness.py` if
  importing a test module is disallowed.
  - The fake `mctl-agents-investigate` CWFT runs the real producer functions. On call 1
    it runs `_seal_draft` against a temp proposal directory containing a model-style
    `draft.json`, using the workflow's actual id and run id taken from the CWFT params.
    It then hands the resulting `request.json` to the fake `find_human_input_request`.
  - On call 2 it asserts that `params["human_input_responses"]` parses through
    `_parse_human_input_responses`, carries the sealed `request_id` and `request_hash`,
    and renders in `_human_input_prompt_block`. It produces no new draft, so
    `find_human_input_request` returns the answered request and the workflow skips it as
    resolved, or returns `None`.
  - The test asserts this sequence: `WAITING_FOR_INPUT` (query), the signal, two
    investigate calls, `human_input_state.state == RUNNING`, a
    `WAITING_FOR_APPROVAL`-equivalent park with no implementer call yet, then `approve`,
    and finally that the implementer ran and `result.human_input.outcome == "answered"`.
- **Live runbook.** Add `docs/runbooks/human-input-e2e.md` with these steps:
  - Prerequisites: the CWFT parameter, the mctl-api allow-list, the profile grant, and
    the Telegram adapter.
  - Open a deliberately ambiguous `agents:intake` test issue.
  - Run `mctl_trigger_issue use_temporal=true`.
  - Watch `human_input_state`.
  - Answer through Telegram, or through `temporal workflow signal ... human_input_response`.
  - Verify the second investigate run, `answered.json` and the approval park.
  - Record the evidence on #473.
- Update ADR 013's "Producer" line and the activity module docstring, both of which
  currently say the producer is not built yet.

## Alternatives

1. **Expose `human.request_input` as a real SDK or MCP tool the model calls.** This was
   dropped. ADR 013 and `options.py` deliberately keep it as a capability flag that never
   reaches `allowed_tools`, and `validate_manifest.py` enforces that. A tool call also
   could not be sealed by the orchestrator without trusting model-supplied identity.
2. **Have the model write `request.json` directly.** This was dropped. The model would
   have to compute hashes and would control `execution`, `requested_from` and
   `expires_at`, which are exactly the fields the contract must bind to the
   orchestrator. A draft that the orchestrator seals keeps the model to the question,
   the reason and the response shape only.
3. **Skip the triplet when asking, and add a new `.status.yaml` state such as
   `awaiting-input`.** This was dropped. It touches every status consumer (reconciler,
   implementer, shepherd) and the forged-approval guard in `_status_disagreements`, all
   for a state the workflow already tracks durably as `WAITING_FOR_INPUT`. Keeping the
   status at `proposed` reuses the existing overwrite rule.
4. **Prove the path only with a live run.** This was dropped as the sole evidence
   because it is not repeatable and depends on two cross-repo prerequisites. It stays
   as the runbook complement.

## Platform impact

- **Migrations.** None. There is no schema change in `human_input.py` and no Temporal
  workflow code change, so no new `workflow.patched` marker and no replay risk. The new
  gitops files live only under `proposals/<slug>/human-input/`.
- **Backward compatibility.** Every new branch is gated on
  `plan_grants_human_input(plan)` or on the presence of `--human-input-responses`.
  Legacy resolver mode and ungranted profiles produce the identical prompt and output;
  a test pins this. An older CWFT that does not forward the parameter simply never
  supplies answers.
- **Cross-repo prerequisites (live only).**
  - mctl-gitops: the `mctl-agents-investigate` CWFT must declare `human_input_responses`
    and pass it as `--human-input-responses`.
  - mctl-api: the parameter must be on the allow-list.
  - mctl-telegram#571: the Telegram adapter.

  The runbook lists all three. Note that until the CWFT forwards the parameter, a live
  continuation would re-ask the question. The workflow already skips that by
  `question_hash` and then proceeds to approval, so the failure is benign rather than a
  hang.
- **Resource impact.** At most `MAX_CLARIFICATION_ROUNDS` extra investigate runs per
  issue, roughly $3 each, which the workflow already bounds. There is one extra field in
  the `gh` call.
- **Risks and mitigations.**
  - Prompt injection through the answer `value`: it is rendered as untrusted data inside
    neutralized tags, exactly like the issue body.
  - The model abusing clarification to stall: the prompt says "genuinely blocked only",
    the triplet is still required, and the round count and TTL are bounded by both the
    producer and the workflow.
  - Leaking question or answer text into logs: only `request_log_dict` is logged, and a
    test greps captured logs.
  - An unauthorized respondent: `validate_response` checks `actor_refs`, and the
    producer refuses to seal without an issue author.
  - A stale `request.json` carried forward: it is excluded on continuation and the
    `answered.json` marker is written in its place.
