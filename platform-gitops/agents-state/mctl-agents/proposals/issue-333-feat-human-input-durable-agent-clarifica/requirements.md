# Durable agent clarification loop: `HumanInputRequest`/`HumanInputResponse` and `WAITING_FOR_INPUT`

## Context

`mctl-agents` already has one durable human-in-the-loop primitive: **authorization**.
`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py:712`) parks on
`await workflow.wait_condition(lambda: self._approved)` (line 827) until the
`approve` signal (line 787) arrives, then runs the `mctl-agents-approve` CWFT.
That answers "is this exact action authorized?". It does not answer the other
question an agent hits constantly: "I do not have enough information to continue
reliably — what is the answer?".

Today an investigator that meets a genuinely ambiguous requirement has to guess,
because there is no way to ask. Issue #333 asks for the missing primitive: a
versioned `HumanInputRequest`/`HumanInputResponse` contract, a first-class
`WAITING_FOR_INPUT` workflow state distinguishable from `WAITING_FOR_APPROVAL`,
a durable wait that releases the Argo/model pod, eligibility gated by the
resolved `ExecutionPlan`, dedupe and loop controls, and tests. The issue's
"DevLoop implementation boundary (2026-09-19)" scopes this proposal to
`mctlhq/mctl-agents` only: the response/read-model API (`mctl-api#261`), the
Telegram surface (`mctl-telegram#571`) and the catalog profile grant
(`mctl-gitops#1277`) are separate work items, and this core must be provable by
tests alone with no operator step and no sibling-repo edit.

## User stories

- AS an issue-investigator agent I WANT to emit a durable, typed question and
  terminate my step SO THAT an ambiguous requirement is resolved by a human
  instead of guessed, without holding a model process open.
- AS the `DevLoopWorkflow` I WANT a `WAITING_FOR_INPUT` state distinct from
  `WAITING_FOR_APPROVAL` SO THAT automation, queries and traces can tell
  "blocked on missing information" apart from "blocked on authorization".
- AS a platform operator I WANT a clarification answer to become attributed
  evidence and never an authorization token SO THAT `"use B and merge it"`
  supplies `B` as data and still leaves the merge behind the approval gate.
- AS a surface adapter author (`mctl-api#261`, `mctl-telegram#571`) I WANT a
  versioned, hash-pinned request/response contract owned by `mctl-agents`
  SO THAT I consume workflow state rather than owning it.
- AS a platform operator I WANT clarification-round, dedupe and timeout limits
  SO THAT a retrying agent cannot spam humans with the same unanswered question.
- AS a release manager I WANT an agent with no `human.request_input` grant in
  its resolved `ExecutionPlan` to behave exactly as it does today SO THAT this
  core can merge before the catalog rollout in `mctl-gitops#1277`.

## Acceptance criteria (EARS)

### Contract and identity

- WHEN a `HumanInputRequest` is sealed THE SYSTEM SHALL assign
  `request_id = "hir-" + request_hash[7:23]` and
  `request_hash = "sha256:" + sha256(canonical JSON of every field except
  `request_id`, `request_hash` and `created_at`)`, mirroring the existing
  `seal()`/`_hash_bytes` convention in `orchestrator/context_snapshot.py:885`.
- WHEN a `HumanInputRequest` or `HumanInputResponse` document is parsed THE
  SYSTEM SHALL reject any unknown key and any unsupported `api_version`,
  matching `_reject_unknown_keys` / `SUPPORTED_API_VERSIONS`
  (`orchestrator/context_snapshot.py:42,92`).
- WHILE a request exists THE SYSTEM SHALL carry `work_item_id`, the Temporal
  `workflow_id`/`run_id`, `argo_workflow_name`, `agent`,
  `definition_version`, `profile_version`, `release_revision` and
  `target_repository_sha`, reusing the field set of
  `ExecutionCorrelation` (`orchestrator/context_snapshot.py:406`).
- WHEN a request declares `response.type` THE SYSTEM SHALL accept only
  `free_text | single_choice | multi_choice | structured`, and SHALL require a
  non-empty `options` list for `single_choice`/`multi_choice`.
- IF a request carries a `context_refs` entry that is not a reference
  (`github:`, `gitops-file:`, `context_snapshot:`, `evidence:`) THEN THE SYSTEM
  SHALL reject the request, so no raw payload is smuggled into it.
- WHEN a request is sealed THE SYSTEM SHALL require a non-empty `question`, a
  non-empty `reason`, and an `expires_at` strictly after `created_at` and no
  further out than `MAX_REQUEST_TTL`.

### Eligibility

- IF the resolved `ExecutionPlan.tools` (`orchestrator/resolver.py:247`) does
  not grant the `human.request_input` capability THEN THE SYSTEM SHALL refuse
  to emit a request, SHALL discard any request artifact the model wrote, and
  SHALL complete the step exactly as it does today.
- WHILE `ISSUE_INVESTIGATOR_RESOLVER_MODE` is not `declarative` THE SYSTEM
  SHALL treat the capability as ungranted, because the legacy builder
  (`orchestrator/options.py:build_issue_investigator_options`) has no plan to
  read eligibility from.
- WHEN eligibility is granted THE SYSTEM SHALL add the capability's tool name
  to `allowed_tools` only when the mctl MCP surface is actually configured,
  matching the existing two-fact conjunction documented at
  `orchestrator/options.py:425`.

### Yield and pod release

- WHEN an eligible agent step emits a valid request THE SYSTEM SHALL finish the
  step with outcome `needs_input`, SHALL NOT poll for an answer, and SHALL
  return from `_run_agent` so the process exits and the Argo pod terminates.
- WHILE a workflow is in `WAITING_FOR_INPUT` THE SYSTEM SHALL hold no Argo
  workflow, no Claude Agent SDK session and no activity slot for that loop.
- WHEN a step emits more than `MAX_OUTSTANDING_REQUESTS_PER_EXECUTION` requests
  THE SYSTEM SHALL keep the first and reject the rest with a typed error.

### Durable wait and state

- WHEN `DevLoopWorkflow` observes a `needs_input` outcome from the investigate
  step THE SYSTEM SHALL enter `WAITING_FOR_INPUT` and SHALL await a
  `human_input_response` signal, a cancel, or the request deadline.
- WHILE in `WAITING_FOR_INPUT` THE SYSTEM SHALL answer the `human_input_state`
  query with the pending `request_id`, `request_hash`, `question_hash`,
  `expires_at`, `round` and the state string `WAITING_FOR_INPUT`, which SHALL
  never equal the approval state string `WAITING_FOR_APPROVAL`.
- WHEN a valid response is signalled THE SYSTEM SHALL move to `RUNNING`, record
  `resume_count`, and launch a fresh continuation step.
- IF no response arrives before `expires_at` THEN THE SYSTEM SHALL move to
  `INPUT_TIMED_OUT` and SHALL end the loop with that outcome recorded in
  `DevLoopResult`, rather than waiting forever.
- IF the request is cancelled or superseded by a newer request for the same
  execution THEN THE SYSTEM SHALL stop honouring the older `request_id`.
- WHILE replaying a history recorded before this change THE SYSTEM SHALL take
  the pre-change command sequence, gated by `workflow.patched("human-input")`,
  so no in-flight loop is wedged by a nondeterminism error.

### Response validation

- WHEN a `HumanInputResponse` is submitted THE SYSTEM SHALL accept it only if
  its `request_id` matches the pending request, its `request_hash` matches that
  request's hash exactly, and the request has not expired.
- IF a response carries a `request_hash` that does not match THEN THE SYSTEM
  SHALL reject it and SHALL NOT resume.
- IF a response's `respondent` is not in the request's resolved
  `requested_from` audience THEN THE SYSTEM SHALL reject it as unauthorized.
- WHEN the same response is delivered more than once THE SYSTEM SHALL treat
  every delivery after the first as an idempotent no-op — one resume, one
  `resume_count` increment.
- IF a second, different response arrives for an already-answered request THEN
  THE SYSTEM SHALL keep the first answer (deterministic first-answer policy)
  and SHALL record the rejection.
- WHEN a response value is validated against `response.type` THE SYSTEM SHALL
  reject a value outside the declared `options` for a choice-typed request.

### Dedupe and loop controls

- WHEN a request is sealed THE SYSTEM SHALL compute
  `question_hash = sha256(normalized question + normalized response spec)`.
- IF an agent emits a request whose `question_hash` equals that of a request
  already outstanding or already answered in this execution THEN THE SYSTEM
  SHALL NOT create a new request; for an answered one it SHALL surface the
  existing answer, and for an outstanding one it SHALL return the existing
  `request_id`.
- WHILE a step is retried by `SDK_STEP_RETRY_POLICY`
  (`dev_loop.py:95`) THE SYSTEM SHALL deliver the same `request_id` rather than
  a duplicate question.
- IF the execution has already completed `MAX_CLARIFICATION_ROUNDS` THEN THE
  SYSTEM SHALL refuse further requests and SHALL fail the step with a typed
  `clarification_rounds_exhausted` error.

### Continuation and provenance

- WHEN the workflow resumes THE SYSTEM SHALL pass the answer to the
  continuation step as a `human_input_response` parameter carrying only
  `request_id`, `request_hash`, `value`, `respondent` reference, `surface` and
  `received_at`, and never the surface transcript.
- WHEN a continuation step assembles its context THE SYSTEM SHALL record the
  answer as a `ContextSource` of kind `human-input-response` with
  `trust: reported`, plus an `EvidenceRef`
  (`orchestrator/context_snapshot.py:583`), and SHALL seal a new
  `ContextSnapshot` whose `snapshot_id` differs from the pre-wait one.
- WHILE building the continuation prompt THE SYSTEM SHALL wrap the answer in
  the untrusted-DATA envelope already used for issue bodies
  (`_neutralize_prompt_tags`, `run_issue_investigator.py:1098`) and SHALL state
  that the answer is human-supplied information which does not waive policy,
  authorization or approval.
- WHEN a continuation step runs THE SYSTEM SHALL mark the answered
  `question_hash` as resolved so the agent does not re-ask it.
- IF a clarification answer contains text that reads as an approval THEN THE
  SYSTEM SHALL NOT set `self._approved`; only the `approve` signal SHALL.

### Observability

- WHEN each lifecycle transition occurs THE SYSTEM SHALL emit exactly one of
  `human_input.requested`, `human_input.wait_started`, `human_input.delivered`,
  `human_input.responded`, `human_input.resumed`, `human_input.timed_out`,
  `human_input.cancelled`.
- WHILE emitting those events THE SYSTEM SHALL include only safe metadata —
  `request_id`, `request_hash`, `question_hash`, `request_version`, work
  item/workflow/execution IDs, agent and profile version, surface, respondent
  identity reference, wait duration, outcome and the before/after
  `snapshot_id` — and SHALL NOT include the question or answer text.

## Out of scope

- Any change to a repository other than `mctlhq/mctl-agents`. The catalog grant
  (`mctl-gitops#1277`), the response/read-model endpoints (`mctl-api#261`) and
  the Telegram surface (`mctl-telegram#571`) are separate work items.
- Replacing or weakening the `#198` approval semantics in
  `DevLoopWorkflow.approve`.
- A live end-to-end pilot through a real Telegram operator. The E2E in the
  issue's "First E2E" section cannot run until the two sibling work items land;
  this proposal delivers the deterministic equivalent under the Temporal test
  environment and the replay harness.
- Applying the capability to the implementer, shepherd, incident-responder,
  mentor or service agents. This core wires exactly one producer — the
  issue-investigator — and one consumer — `DevLoopWorkflow`.
- A general evidence store. `#199` is referenced by `EvidenceRef` only.
- Holding a model or Argo pod open for any part of the wait.

## Open questions

- **ADR number.** The issue names ADR-009, but `docs/adr/009-context-snapshot-contract.md`
  and `docs/adr/010-lifecycle-ownership-contract.md` already exist. This
  proposal writes **ADR-011**, `docs/adr/011-human-input-contract.md`, and
  cross-references it from the issue. Renumbering a merged ADR is not an
  option; a reviewer who disagrees should say so before implementation.
- **Transport of the request out of the Argo pod.** The workflow reads
  `WorkflowResult` (`activities/argo.py:71`), which exposes only
  `phase` — there is no `outcome` channel from the pod to Temporal, and adding
  one to mctl-api is out of boundary. This proposal has the agent write the
  sealed request into `$PROPOSAL_DIR/human-input/`, which the existing
  investigate CWFT already commits to gitops, and has the workflow read it back
  through a new GitHub-contents activity modelled exactly on
  `find_proposal_slug` (`activities/proposals.py:61`). If a reviewer prefers a
  new mctl-api outcome field, that is a cross-repo change and a different
  proposal.
- **Threading the answer into the continuation CWFT.** The continuation passes
  a new `human_input_response` parameter to `mctl-agents-investigate`. That
  parameter must exist in the sibling CWFT before it can be submitted — the
  same known cross-repo coupling already documented for the `service` parameter
  at `dev_loop.py:938-949`. The ordering is self-consistent: with no catalog
  grant no request is ever created, so the parameter is never sent, and the
  loop behaves exactly as today. The rollout order is `mctl-gitops#1277` after
  this core.
- **`requested_from` resolution.** Who may answer is ultimately mctl-api's
  identity question. This core stores the audience (`work_item_owner`,
  `repo_operators`, `tenant_operators`) plus an explicit allow-list of actor
  references on the request, and validates a response against that stored
  list. Richer role resolution belongs to `#242`/`mctl-api#261`.
- **`ContextSource.kind` vocabulary.** ADR 009 sec. 6 declares a closed source
  kind set. Adding `human-input-response` extends it. This proposal treats that
  as an additive change within `context.mctl.ai/v1alpha1` (new enum member, no
  field change, `from_dict` still rejects unknown keys), and says so in
  ADR-011. If a reviewer reads the closed set as requiring an `apiVersion`
  bump, the alternative is an `EvidenceRef`-only linkage with no new source
  kind, which loses the byte-accounting the snapshot budget gives.
- **Timeout defaults.** The issue gives `24h` as an illustrative timeout. This
  proposal defaults `DEFAULT_REQUEST_TTL = 24h`, caps `MAX_REQUEST_TTL = 7d`,
  and sets `MAX_CLARIFICATION_ROUNDS = 3` and
  `MAX_OUTSTANDING_REQUESTS_PER_EXECUTION = 1`. All four are module constants,
  chosen rather than measured; they are the numbers to argue about in review.
