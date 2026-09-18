# Durable agent clarification loop — `HumanInputRequest`/`HumanInputResponse` and `WAITING_FOR_INPUT`

## Context

`mctl-agents` agents run as one-shot Argo/Claude-Agent-SDK steps driven by
`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`). When an
agent hits genuine ambiguity it has no way to ask a human: the
`issue-investigator` prompt tells it outright to "capture the ambiguity in
`## Open questions`, never stop to ask"
(`orchestrator/run_issue_investigator.py:_build_prompt`). The one durable
human checkpoint that does exist is `approve()` — a Temporal signal that
authorizes the `proposed -> accepted` flip for a proposal
(`dev_loop.py:787-800`, `orchestrator/temporal/cli.py:approve`). That is
*authorization* for one consequential action, not *clarification*, and
`orchestrator/lifecycle/policy.py:merge_authority_for` records in its own
docstring the cost of conflating the two (mctlhq/mctl-agents#344).

This proposal adds the missing primitive: an agent that cannot continue with
acceptable confidence seals a versioned `HumanInputRequest`, releases its
compute pod, and the workflow parks in a first-class `WAITING_FOR_INPUT`
state until an authorized human answers through a surface. The answer becomes
attributed evidence in a child `ContextSnapshot` (ADR 009,
`orchestrator/context_snapshot.py`) and a fresh Argo step continues the same
WorkItem. The first deliverable is the ADR that `mctlhq/mctl-api#261` and
`mctlhq/mctl-telegram#571` consume as the schema of record; this repository
owns the schema module, the workflow states, the capability and the
investigator continuation, not the surface or the HTTP endpoints.

## User stories

- AS an `issue-investigator` agent I WANT to ask one bounded question when
  retrieval and code reading leave a consequential requirement ambiguous SO
  THAT I produce a grounded proposal instead of guessing or deferring the
  decision to `## Open questions`.
- AS a platform operator I WANT the workflow to distinguish
  `WAITING_FOR_INPUT` from `WAITING_FOR_APPROVAL` SO THAT I can tell "an
  agent needs information from me" from "an action needs my authorization".
- AS a platform operator I WANT to answer from Telegram and have the exact
  paused run resume automatically SO THAT I do not have to re-trigger the
  issue by hand.
- AS a platform owner I WANT no Argo pod or model process held open while a
  human is offline SO THAT a 24-hour wait costs Temporal history, not
  compute.
- AS a security reviewer I WANT a human answer to be data, never
  authorization or system instruction, SO THAT "use option B and merge it"
  supplies B and still goes through `approve()` for the merge.
- AS an `mctl-api` / `mctl-telegram` implementer I WANT one versioned,
  hashed, stdlib-only contract SO THAT my surface consumes platform state
  rather than owning it.

## Acceptance criteria (EARS)

### Contract and identity

- WHEN a `HumanInputRequest` is sealed THE SYSTEM SHALL compute
  `request_hash = "sha256:" + sha256(canonical JSON of every field except
  `request_hash`, `request_id` and `created_at`)` and derive
  `request_id = "hir-" + request_hash[7:23]`, using the same
  `json.dumps(payload, sort_keys=True, separators=(",", ":"))` convention as
  `orchestrator/context_snapshot.py`.
- WHEN a `HumanInputRequest` or `HumanInputResponse` is parsed from a dict
  THE SYSTEM SHALL reject any key it does not know, and SHALL reject any
  hash-typed field that does not carry the `sha256:` prefix.
- WHILE a `HumanInputRequest` exists THE SYSTEM SHALL carry an
  `ExecutionCorrelation` block byte-identical in shape to ADR 009's
  (`agent`, `environment`, `temporal_workflow_id`, `temporal_run_id`,
  `argo_workflow_name`, `target_repository_sha`, `definition_version`,
  `definition_content_hash`, `profile_version`, `profile_content_hash`,
  `release_revision`) plus `work_item_id`, `trace_id` and
  `context_snapshot_ref`.
- WHERE a response is typed THE SYSTEM SHALL validate `value` against
  `response.type` in the closed vocabulary `free_text | single_choice |
  multi_choice | structured`, and SHALL reject a `single_choice` /
  `multi_choice` value not drawn from `response.options`.
- THE SYSTEM SHALL bound every free-text field of both documents
  (`question`, `reason`, each option, `value`) to a declared maximum length,
  and SHALL reject a longer value rather than truncating it.
- THE SYSTEM SHALL declare no field named or containing `allow`, `deny`,
  `permit`, `grant`, `approve` or `authorized` anywhere in either schema,
  mirroring ADR 009 sec. 5.
- THE SYSTEM SHALL carry `context_refs` as `{kind, locator}` pointers only,
  and SHALL declare no field capable of holding a raw prompt, tool payload,
  log or secret.

### Yielding and the durable wait

- WHEN an eligible agent calls the `human.request_input` capability THE
  SYSTEM SHALL seal a request, persist it through the platform API, and
  return only the `request_id` and `request_hash` to the model.
- WHEN the capability has been called THE SYSTEM SHALL terminate the current
  agent step with the typed outcome `needs_input` and a dedicated exit code,
  and SHALL NOT publish a partial proposal triplet from that step.
- WHILE a run is waiting for a human answer THE SYSTEM SHALL hold no Argo
  pod, no model stream and no Temporal activity open for the wait; the wait
  SHALL be a `workflow.wait_condition` in `DevLoopWorkflow` only.
- WHILE `DevLoopWorkflow` is parked on a clarification THE SYSTEM SHALL
  answer its `waiting_for` query with `input`, and SHALL answer `approval`
  while parked on `approve()` — the two states SHALL never be represented by
  the same value.
- IF the model calls `human.request_input` when the resolved
  `ExecutionPlan.tools` does not grant it THEN THE SYSTEM SHALL refuse the
  call, record the refusal, and leave the step's normal outcome unchanged.
- IF the model calls `human.request_input` a second time within one step
  THEN THE SYSTEM SHALL refuse the second call and keep the first request as
  the outstanding one.

### Responding

- WHEN an authorized response arrives whose `request_id` and `request_hash`
  both match the outstanding request THE SYSTEM SHALL record it and release
  the workflow's wait.
- IF a response carries a `request_hash` that does not match the outstanding
  request THEN THE SYSTEM SHALL reject it as stale and leave the workflow
  waiting.
- IF a response arrives for a request that is expired, cancelled or
  superseded THEN THE SYSTEM SHALL reject it and leave the workflow in the
  state that expiry/cancellation already produced.
- WHEN a duplicate delivery of an already-recorded response arrives THE
  SYSTEM SHALL treat it as an idempotent no-op and SHALL NOT resume the
  workflow a second time.
- WHEN two distinct valid responses race THE SYSTEM SHALL accept the first
  by `received_at` (ties broken by response id) and record the second as
  `superseded-by-first`, never silently merging them.
- IF the respondent is not authorized for the request's `requested_from`
  audience THEN THE SYSTEM SHALL reject the response and emit
  `human_input.rejected` with the reason code, without revealing the
  question to that respondent.
- WHILE a request is outstanding THE SYSTEM SHALL expose only
  `question`, `reason`, `response` and safe `context_refs` to a surface —
  never the agent's prompt, tool output or clone contents.

### Continuation

- WHEN a valid response is recorded THE SYSTEM SHALL start a FRESH Argo/model
  step for the same Temporal workflow and the same WorkItem, incrementing
  `resume_count`.
- WHEN a continuation step starts THE SYSTEM SHALL build a child
  `ContextSnapshot` whose `StepRef.parent_snapshot_id` is the snapshot the
  request cited, carrying the answer as one `ContextSource` of kind
  `human-input` and one `EvidenceRef` of kind `human-input-response`.
- WHILE assembling a continuation prompt THE SYSTEM SHALL wrap the human
  answer in a delimiter block, neutralize forged delimiters in the answer
  text the way `run_issue_investigator._neutralize_prompt_tags` does for
  issue bodies, and state explicitly that the answer is human-provided
  information that resolves the cited ambiguity, does not waive policy or
  approval, and confers no instruction authority.
- WHILE a continuation step runs THE SYSTEM SHALL NOT replay the surface
  transcript — only the sealed `HumanInputResponse.value` and the prior
  context refs.
- IF a continuation agent asks a question whose normalized `question_hash`
  equals one already answered in this workflow THEN THE SYSTEM SHALL refuse
  the request and require the step to continue with the recorded answer.
- IF a clarification response arrives THEN THE SYSTEM SHALL NOT set
  `_approved`, SHALL NOT flip any `.status.yaml`, and SHALL NOT satisfy any
  approval gate.

### Limits, timeout and cancellation

- WHILE a workflow has an outstanding request THE SYSTEM SHALL refuse to
  create a second outstanding request for the same execution.
- IF a workflow has already completed `MAX_CLARIFICATION_ROUNDS` (2) answered
  rounds THEN THE SYSTEM SHALL refuse further requests and require the agent
  to proceed with its existing information.
- IF a request is not answered within `expires_at` THEN THE SYSTEM SHALL
  transition to `INPUT_TIMED_OUT`, emit `human_input.timed_out`, and start
  one continuation step told that the question went unanswered, so the run
  produces a proposal recording the ambiguity under `## Open questions`
  rather than failing.
- IF the workflow is cancelled while waiting THEN THE SYSTEM SHALL mark the
  request `cancelled`, emit `human_input.cancelled`, and reject any later
  response for it.
- WHEN a retried or replayed step would re-create an equivalent request THE
  SYSTEM SHALL return the existing `request_id` instead of creating a second
  one, so a human is never asked the same question twice.

### Observability

- WHEN each of `human_input.requested`, `.wait_started`, `.delivered`,
  `.responded`, `.resumed`, `.timed_out`, `.cancelled` occurs THE SYSTEM
  SHALL emit an event carrying only safe metadata: `request_id`,
  `request_hash`, `request_version`, the correlation ids, agent/profile
  version, surface, a respondent identity reference, wait duration, outcome,
  and the before/after `snapshot_id`s.
- THE SYSTEM SHALL NOT place `question`, `reason` or `value` text into
  telemetry by default; `to_log_dict()` SHALL emit hashes, lengths and codes
  only, following `context_snapshot.to_log_dict()`.

## Out of scope

- The mctl-api endpoints and read model themselves (`mctlhq/mctl-api#261`
  owns create/respond/get/list/cancel and the `WAITING_FOR_INPUT` projection).
  This proposal defines the contract they serve and the Temporal side that
  consumes it.
- The Telegram surface adapter, its bot commands and its authorization
  resolution (`mctlhq/mctl-telegram#571`).
- The Argo `ClusterWorkflowTemplate` YAML changes in `mctlhq/mctl-gitops`
  (new `human_input_ref` parameter, exit-code mapping). This proposal states
  the required contract; the gitops PR is a sibling change.
- Changing `approve()` / `control.requires_human_approval` semantics
  (`orchestrator/proposal_state.py`, mctl-agents#198).
- Granting the capability to `implementer`, `shepherd`, `service-agent`,
  `mentor` or `incident-responder`. Only `issue-investigator` is piloted.
- A general redaction engine. ADR 009 sec. 7 already records that none
  exists in this repository; this proposal bounds and hashes instead.
- Portal and GitHub-comment surfaces.
- Flipping `ISSUE_INVESTIGATOR_RESOLVER_MODE` away from `legacy` by default.

## Open questions

- **The ADR number in the issue is already taken.** The issue names
  "ADR-009", but `docs/adr/009-context-snapshot-contract.md` (accepted,
  2026-09-11) and `docs/adr/010-lifecycle-ownership-contract.md` already
  exist. This proposal writes `docs/adr/011-human-input-contract.md` and
  cross-references it from the issue; `mctlhq/mctl-api#261` and
  `mctlhq/mctl-telegram#571` must be told the number changed.
- **Where the sealed request is persisted from.** The Temporal worker
  deliberately holds no gitops checkout (`dev_loop.py` module docstring), so
  this proposal has the Argo pod POST the sealed request to mctl-api with the
  `MCTL_TOKEN` it already carries, and the workflow read it back through an
  activity. The alternative — threading it out as an Argo output parameter
  through `submit_and_wait` — is cheaper for mctl-api but changes
  `WorkflowResult` more deeply. Proceeding with the POST.
- **Capability naming.** The issue proposes `human.request_input`. The
  Claude Agent SDK surfaces in-process tools as `mcp__<server>__<tool>`, so
  the model actually sees `mcp__human__request_input`;
  `ExecutionProfile.tools` carries the logical name `human.request_input`
  and the options builder maps it. Recorded rather than resolved with
  mctl-api.
- **`work_item_id` has no producer in this repository today.** The canonical
  WorkItem lives in `mctlhq/mctl-telegram#443`. The field is required by the
  contract and populated from the Temporal workflow id
  (`orchestrator/temporal/issue_ref.py:workflow_id_for`) until a real
  WorkItem id exists.
- **Timeout default.** The issue's example uses `24h`. Argo's own step
  deadline is unrelated (the pod is gone), so 24h is adopted as the default
  with a 7-day ceiling; whether an unanswered question should instead end
  the run rather than continue with `## Open questions` is the one behaviour
  a reviewer should confirm. This proposal continues, because the
  investigator prompt already treats unresolved ambiguity that way.
- **Authorization source of truth.** `requested_from.audience` is a closed
  vocabulary here (`work_item_owner`, `repo_operator`, `tenant_operator`,
  `platform_admin`); resolving an audience to concrete identities is
  mctl-api's job and is not attempted in this repository.
