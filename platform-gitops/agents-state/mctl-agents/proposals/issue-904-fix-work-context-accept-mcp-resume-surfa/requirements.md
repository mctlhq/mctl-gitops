# Accept the MCP resume surface without inventing client identity

## Context

mctl-api already records `surface=mcp` on WorkItem execution requests created through
the MCP tool `mctl_request_work_item_execution`. The dispatcher in
`orchestrator/temporal/dispatcher.py` forwards that surface unchanged in a
`ResumeDelivery`, with `actor_id` set to the request's authenticated `requested_by`.
`DevLoopWorkflow._resume_provenance` (`orchestrator/temporal/workflows/dev_loop.py`)
checks the surface against the closed `SURFACE_KINDS` vocabulary in
`orchestrator/work_context/contract.py`. That vocabulary is
`{github, telegram, web, cli, api}`, so the workflow refuses every MCP resume with
`surface-or-actor-unrecognised`. The sealed-snapshot schema
(`WORK_CONTEXT_SURFACE_KINDS` in `orchestrator/context_snapshot.py`) and the investigator
CLI (`--surface`) would refuse it too. The tolerant mirror (`answer_from`) classifies an
`origin_surface="mcp"` item as `WORK_ITEM_UNKNOWN`. Both kinds of refusal block real
traffic today.

The issue (parent epic mctlhq/.github#281) asks for three things. First, add `mcp` to
both vocabularies. Second, propagate the canonical surface and actor into the sealed
snapshot. That forwarding is owned by mctl-agents#573 and is only integrated and
regression-tested here. Third, a new worker rule: a pinned resume intent whose text is
unavailable or redacted by retention must park the loop in `WAITING_FOR_INPUT` instead
of running the literal placeholder `[text removed by retention]`. `mcp` is a surface
label only. It never implies a client, session, model or inference-account identity.
The actor is the authenticated principal.

## User stories

- AS an operator using an MCP client I WANT my `resume` execution request to be
  accepted by the live DevLoop SO THAT MCP is a first-class surface like Telegram or
  GitHub.
- AS a platform auditor I WANT the sealed ContextSnapshot to say `current_surface=mcp`
  and `surface_transition=true` when a Telegram-originated item is resumed over MCP SO
  THAT approval re-arming is traceable.
- AS a security reviewer I WANT a switch between model clients (for example Claude and
  Codex) under the same principal on MCP NOT to count as a new actor or as reviewer
  independence SO THAT no authority is invented from a client name.
- AS a requester I WANT a resume whose intent text was removed by retention to stop
  and ask for replacement text SO THAT the agent never acts on a placeholder.

## Acceptance criteria (EARS)

Vocabulary

- WHEN a `resume` signal or `accept_execution_request` Update carries `surface="mcp"`
  with a recognised actor kind THE SYSTEM SHALL accept it and SHALL NOT record
  `surface-or-actor-unrecognised`.
- IF a resume carries a surface outside `{github, telegram, web, cli, api, mcp}` THEN
  THE SYSTEM SHALL refuse it with `surface-or-actor-unrecognised`, as it does today.
- THE SYSTEM SHALL keep `orchestrator.work_context.contract.SURFACE_KINDS` and
  `orchestrator.context_snapshot.WORK_CONTEXT_SURFACE_KINDS` identical. The existing
  parity test in `tests/test_context_snapshot.py` stays and keeps enforcing this.
- WHEN mctl-api returns a WorkItem with `origin_surface="mcp"` THE SYSTEM SHALL classify
  it `WORK_ITEM_FOUND`. The negative example in
  `tests/test_work_context_contract.py::test_out_of_vocabulary_origin_surface_is_unknown`
  SHALL use a still-unknown surface instead.
- WHEN the investigator is invoked with `--surface mcp` THE SYSTEM SHALL accept the
  flag.

Provenance into the snapshot (integrated with #573)

- WHEN an item that originated on `telegram` is resumed with `surface=mcp` THE SYSTEM
  SHALL seal `work_context.current_surface="mcp"` and `surface_transition=true`.
- IF the surface or actor forwarding from the DevLoop into the investigate submission is
  removed THEN the end-to-end regression test SHALL fail. A mutation run proves this.
- IF the current surface or actor provenance is unknown THEN THE SYSTEM SHALL seal it
  as empty or absent, or SHALL refuse to seal. It SHALL NOT report
  `surface_transition=false` as if no transition had been measured.

Identity and approval

- WHILE consecutive executions share the same surface (`mcp`), actor kind and
  authenticated principal THE SYSTEM SHALL NOT treat a change of model or client
  (for example Claude to Codex) as a surface or actor transition.
- THE SYSTEM SHALL NOT derive actor identity, reviewer independence or human identity
  from a model name or client name. `actor_id` SHALL be the authenticated
  `requested_by` principal only.
- WHEN a same-principal MCP resume occurs THE SYSTEM SHALL neither grant new approval
  authority nor invalidate an existing approval on that basis alone. The approval
  SHALL remain usable only while its original content, authority, freshness and
  execution constraints hold.
- IF the approved proposal content changes THEN THE SYSTEM SHALL not release on the old
  approval, whichever client is in use.

Redacted or unavailable pinned intent (new worker behaviour)

- IF the pinned resume intent is `text_redacted` or its text cannot be read THEN THE
  SYSTEM SHALL NOT render or execute `[text removed by retention]` as an instruction.
- WHEN that condition is detected THE SYSTEM SHALL park the loop in
  `WAITING_FOR_INPUT` with a generic, ADR 013-conformant request. Its question and
  reason SHALL reference only IDs (work item, execution request, intent) and SHALL
  contain no intent text.
- WHEN replacement text is supplied THE SYSTEM SHALL accept it only as a new intent
  through mctl-api's authorized intent storage, explicitly rebound to the resume. The
  text SHALL NOT be embedded in the public `human-input/request.json` or the response
  `value`.
- IF the intent becomes redacted after the execution request was enqueued THE SYSTEM
  SHALL apply the same parking behaviour. Request-side refusal belongs to mctl-api#871.

Ownership and legacy

- WHILE a resume is processed THE SYSTEM SHALL preserve the single lifecycle owner and
  fencing epoch (ADR 010). Accepting `mcp` SHALL NOT create a second owner.
- THE SYSTEM SHALL continue to accept the legacy surfaces `github`, `telegram`, `web`,
  `cli` and `api`, and SHALL reject a foreign actor kind.

Rollout

- IF a worker or investigator image without `mcp` in its vocabulary receives a
  `surface=mcp` parameter THEN it SHALL fail closed by refusing, not by sealing a
  wrong or empty provenance. A mixed-version negative test covers this.

## Out of scope

- Implementing the DevLoop-to-CWFT surface and actor forwarding itself. That is
  mctl-agents#573. This proposal integrates with it and adds the end-to-end regression.
- Request-side refusal of redacted intents in mctl-api (mctl-api#871), and mctl-api#868.
- Any live rollout or enabling of new execution admission. This planning phase only
  defines the order.
- Recording client, session, model or inference-account identity anywhere.
- Changes to mctl-gitops CWFT templates. They are listed as a rollout prerequisite
  and are tracked under #573.

## Open questions

- Parameter names for the CWFT forwarding (`surface`, `actor_kind`, `actor_id`) are for
  #573 to fix. This proposal assumes those names and the matching `--surface`,
  `--actor-kind` and `--actor-id` CLI flags that already exist.
- Who answers the redacted-intent `WAITING_FOR_INPUT` request? ADR 013 names the issue
  author. The resume's `requested_by` principal looks more correct, but it may not
  have a GitHub identity. Assumption: name the `requested_by` principal when the
  surface can address it, else the issue author.
- "Explicitly rebound" replacement text: assumed to mean the answer carries only a new
  `intent_id`, which the investigator re-reads from mctl-api and pins in place of the
  redacted one. The exact rebinding API (an intent field or a new execution request)
  may need mctl-api#871 input.
- Mutation testing tooling is not in the repo today. Assumption: a scripted mutation
  (a test that monkeypatches the forwarding out and asserts the failure) is enough.
- mctl-api#353's sweeper is related. Fixtures here do not prove it shipped.
