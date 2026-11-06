# Spike: journey-level correlation across governed execution (`mctl.intent.id`)

## Context

Issue mctlhq/.github#306 asks whether MCTL needs a journey-level correlation identity,
called `mctl.intent.id` for now. It would sit above `trace_id`, request correlation id,
`work_item_id`, `execution_id`, Temporal ids, approval refs and content hashes. The goal is
to query one governed delegation (intent -> policy -> approval -> executions/retries -> side
effect) as a whole, even when it spans several traces. The idea comes from LinkedIn's
OpenTelemetry journey design. The spike must give a GO / NO-GO, an identity map, a worked
multi-trace journey, a decision on coordinated sampling, and a minimal rollout that reuses
existing owners.

This matters because MCTL already has several identities with different lifetimes. Adding
another one without a proven need would break the `.github#55` invariant (observability
reuses canonical execution identity and does not become a second correlation scheme). It
would also risk the `mctl-api#701` / `.github#182` invariant (sampled telemetry is not the
governance record).

Existing material already points toward reuse. The WorkItem contract (`wi_`, documented by
the mctl MCP tools) has the right properties for a journey identity:

- mctl-api mints it, and it is tenant scoped.
- It holds an append-only list of intents, many executions (`we_`), execution requests
  (`xr_`) and sealed ContextSnapshots (`cs_`) that chain resumes.
- The approval `intent_hash` already binds `work_item_id` (see
  `docs/spikes/agent-governance-decision-assurance.md` sections 5-8 and the
  `issue-182` proposal design).

The spike has to confirm or refute this with evidence, and must not assume it.

## User stories

- AS a platform operator I WANT one stable key per governed delegation SO THAT I can list
  every trace, execution, approval, retry and side effect that came from it.
- AS a governance reviewer I WANT to go from a side effect to the approval/policy decision
  that authorized it SO THAT I can answer "who allowed this" from durable records, not
  sampled spans.
- AS the observability owner (`mctl-docs` attribute catalog, mctl-gitops collector) I WANT
  a written decision on whether a new attribute is needed SO THAT nobody adds a parallel
  correlation scheme.
- AS the roadmap owner I WANT the spike recorded as a `SpikeDefinition` with a report and a
  proposed verdict SO THAT the decision and follow-ups can be traced in Git.

## Acceptance criteria (EARS)

- WHEN the spike report `docs/spikes/journey-intent-correlation.md` is merged THE SYSTEM
  SHALL contain exactly one proposed verdict out of `REUSE_WORK_ITEM_ID`, `ADOPT_INTENT_ID`
  and `NO_CHANGE`, and state that verdict as a GO or NO-GO on `mctl.intent.id`.
- WHEN the report lists candidate identifiers THE SYSTEM SHALL compare at least `trace_id`,
  the ingress request correlation id, `work_item_id`, `execution_id` (and its attempt/
  sequence), Temporal workflow id and run id, `aar_` approval refs, `intent_hash` /
  `artifact_hash` / proposal content digest, WorkItem intent entries and the
  `mctl-api#701` decision-record identity. Each row SHALL give the minting owner, lifetime,
  trust (asserted or propagated), whether it spans multiple traces, and an evidence tag
  (`[CODE]`, `[DOC]`, `[DEPLOYED]` or `unknown (not observed)`).
- IF an existing identifier is proposed as the journey identity THEN THE SYSTEM SHALL cite
  its documented lifetime and trust semantics before reusing it, and SHALL list the paths
  where it is absent today (for example direct approve P2 and incident responder P3 in the
  `.github#182` report).
- IF the verdict is `ADOPT_INTENT_ID` THEN THE SYSTEM SHALL define the event that mints it,
  the authoritative minter, its boundary (instruction, objective or decision), behaviour on
  retry, resume, `continue_as_new` and material amendment, its relation to content hashes,
  the parent/child representation, the propagation contract, and the OTel attribute
  placement. A name that does not collide with WorkItem intents or `intent_hash` SHALL be
  chosen.
- WHILE any verdict is proposed THE SYSTEM SHALL keep the journey identity separate from
  `trace_id`, request id, execution identity, content hashes and approval identities. It
  SHALL never be treated as an authorization capability or as proof of approved content.
- WHILE any verdict is proposed THE SYSTEM SHALL keep durable records (audit events,
  `action_approval_requests`, WorkItem executions, `.status.yaml`) as the governance source
  of truth. Every operator query SHALL say which part comes from durable records and which
  from sampled telemetry.
- WHEN the report describes the propagation path (ingress/MCP -> mctl-api -> decision/
  approval -> Temporal -> Argo -> runtime -> MCP/tool -> GitHub/platform mutation ->
  evidence) THE SYSTEM SHALL mark, for each boundary, whether the journey key is asserted,
  propagated, absent or `unknown (not observed)`.
- WHEN the report gives the worked journey THE SYSTEM SHALL show at least two distinct
  `trace_id`s under one journey key, with an approval/decision boundary between them, and
  SHALL label each fact observed or illustrative.
- WHEN the report decides on coordinated journey sampling THE SYSTEM SHALL record
  `ADOPT`, `DEFER` or `REJECT` with privacy, cardinality and cost analysis. The analysis
  SHALL take the deployed workflow-type head sampling (`MCTL_TRACE_WORKFLOW_TYPES:
  DevLoopWorkflow`) as the baseline.
- IF correlation would require prompts, completions, Telegram message bodies, tool payloads
  or other private content THEN THE SYSTEM SHALL reject that design. Only opaque ids and
  digests may be used.
- WHEN the report proposes follow-ups THE SYSTEM SHALL name one owning repository per
  follow-up and check it against existing correlation issues (`mctl-api#285`,
  `mctl-agent#97`, `mctl-agents#195/#196`, `mctl-telegram#617`, `mctl-docs#116`,
  `mctl-api#701`). It SHALL NOT open implementation issues before the owner records the
  decision.
- WHEN the spike manifest `roadmap/spikes/journey-intent-correlation.yaml` is added THE
  SYSTEM SHALL pass `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`. The
  manifest SHALL have `lifecycle: proposed` and no `decision` block.

## Out of scope

- Implementing any identifier, attribute, propagation or sampler change.
- Replacing W3C trace context, reselecting the trace backend (Tempo, `.github#55` /
  mctl-gitops#1280), or copying LinkedIn's Kafka/ClickHouse pipeline.
- Designing a new approval, policy, authorization or evidence framework. Those belong to
  `.github#181` and `mctl-api#701`.
- Recording the owner's decision in the manifest. The owner records it, not the agent.
- Storing prompts, completions or payloads for correlation.

## Open questions

- Is `MCTL_SUBMIT_CREATES_EXECUTION` enabled on the deployed mctl-api? The
  `mctl_trigger_issue` contract says it is off by default. When it is off, a DevLoop run is
  not recorded as an execution of the issue's WorkItem, so `wi_` would not cover today's
  main governed path. The gitops checkout available here has no mctl-api values, so this
  run could not observe the setting. The spike must read it, or record it as unknown.
- Is `mctl.work_item.id` already in the `mctl-docs#116` attribute catalog, and does the
  DevLoop producer emit it? The issue implies `mctl.work_item.*` exists, but mctl-docs was
  not read in this run.
- Does one DevLoop render as one long-lived trace across the approval park, or as several
  traces? The `.github#182` report observed a separate trace id (`9706d41d...`) on the
  approve CWFT. This decides how the worked journey's traces are counted.
- Can one user objective span several WorkItems (for example an epic wave, or a Telegram
  request that leads to issues in two repos)? If such a case is real and needs a single
  query key, it is the only evidence that would justify `ADOPT_INTENT_ID`.
  Working interpretation: an epic wave already has the epic and the plan hash as its
  grouping key, so it is not a counterexample.
