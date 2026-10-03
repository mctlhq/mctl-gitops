# Resume the investigator from a canonical WorkItem across surfaces

## Context

Today an investigator run is identified by exactly one thing: the GitHub
issue URL. `orchestrator/temporal/workflows/dev_loop.py:370-372` defines
`IssueRef` with a single field (`issue_url`); `workflow_id_for` in
`orchestrator/temporal/issue_ref.py:30-37` derives
`dev-loop-mctlhq-<repo>-<N>` from it; and `orchestrator/run_issue_investigator.py`
takes three flags (`--issue-url`, `--state-dir`, `--dry-run`, lines 2075-2094)
with no notion of an execution identity at all — a grep for
`run_id|execution_id|correlation` over that 2129-line module returns nothing.
The de-facto correlation key is the proposal slug on disk. That means a task
cannot outlive one execution: `dev_loop.py:923-936` says so in as many words
("It is a restart, not a resume — the new run re-investigates and waits for a
fresh approve signal"). There is no way for work begun on one surface to be
picked up on another without replaying the original conversation, and nothing
ties two executions of the same task together for trace or evidence purposes.

This proposal adds the missing durable spine in `mctl-agents`: a client-side
mirror of the canonical `WorkItem` contract that mctl-api#227 owns, a
`WorkContextRef` block on the `ContextSnapshot` document
(`orchestrator/context_snapshot.py`) that correlates sibling executions of one
work item, a staged rollout switch modelled on
`orchestrator/lifecycle/rollout.py`, new investigator flags, a pure
canonical-state reconstruction function that never takes a transcript, and a
`resume` signal on `DevLoopWorkflow` whose idempotency, rejection and
approval-re-evaluation semantics are explicit and tested. Temporal remains the
only durable orchestration engine; nothing here introduces a second one.

## User stories

- AS a platform operator I WANT to launch an investigator execution from a
  canonical `WorkItem` reference SO THAT the task's identity is durable and
  independent of the surface that happened to start it.
- AS a user who started work in one surface I WANT to resume the same work
  item from a different surface SO THAT I do not have to restate the task or
  replay the original conversation.
- AS an auditor I WANT every execution to carry its own immutable execution
  identity and sealed `ContextSnapshot`, correlated to one `WorkItem` SO THAT
  a trace or evidence view can show both executions as one task without either
  record having been rewritten.
- AS a security reviewer I WANT a surface or actor transition to force
  re-evaluation of approval SO THAT approval granted by one actor on one
  surface is never silently inherited by another.
- AS a maintainer of the dev-loop worker I WANT resume to be idempotent or
  explicitly rejected SO THAT a duplicated signal or a racing second surface
  cannot fork one work item into two divergent executions.

## Acceptance criteria (EARS)

Contract and identity

- WHEN a caller constructs a `WorkItemRef` from an mctl-api payload THE SYSTEM
  SHALL accept a payload carrying keys it does not recognise and SHALL return
  `None` for a payload missing a required key, mirroring
  `orchestrator/lifecycle/contract.py`'s `from_payload` discipline
  (contract.py:129-137, 166-176).
- WHEN a `WorkItemRef`, `SurfaceRef`, `ActorRef` or `ExecutionRef` is parsed
  and a closed-vocabulary field (`surface.kind`, `actor.kind`,
  `work_item.state`) carries an unrecognised value THE SYSTEM SHALL classify
  the answer as `WORK_ITEM_UNKNOWN` and SHALL NOT fall back to a permissive
  default.
- WHEN an investigator execution starts THE SYSTEM SHALL have exactly one
  `execution_id` for that execution, SHALL derive it deterministically from
  `(work_item_id, execution_sequence, attempt)` when the caller supplies none,
  and SHALL treat it as immutable for the life of the execution.
- WHILE more than one execution exists for one work item THE SYSTEM SHALL keep
  every prior `ExecutionRef` and every prior `ContextSnapshot` byte-identical;
  no resume path SHALL write to, re-seal, or re-hash a historical record.

ContextSnapshot correlation

- WHEN `orchestrator.context_snapshot.seal()` is called with a
  `WorkContextRef` THE SYSTEM SHALL include that block in the canonical JSON
  that produces `content_hash`, so two executions of the same work item that
  differ only in execution identity SHALL seal to different `snapshot_id`s.
- WHEN a `WorkContextRef` is present THE SYSTEM SHALL record
  `work_item_id`, `work_item_revision`, `execution_id`, `execution_sequence`,
  `prior_execution_ids`, `resumed_from_snapshot_id`, `origin_surface`,
  `current_surface`, `actor_kind`, `actor_id` and `surface_transition`.
- IF a `ContextSnapshot` carries a `step` block referencing a parent snapshot
  THEN THE SYSTEM SHALL require its `work_context` block to equal its
  parent's, alongside the existing rule that its `execution` block must equal
  its parent's (`context_snapshot.py:796-805`).
- WHILE a `WorkContextRef` is attached THE SYSTEM SHALL NOT consume any of its
  fields in an authorization decision, preserving ADR 009 sec. 5's boundary
  (`context_snapshot.py:23-27`); the block is provenance metadata only.
- WHEN `to_log_dict()` is called on a snapshot carrying a `WorkContextRef` THE
  SYSTEM SHALL emit `work_item_id`, `execution_id` and `execution_sequence` for
  correlation and SHALL NOT emit `actor_id`.

Rollout staging

- WHEN `WORK_CONTEXT_ROLLOUT_MODE` is unset, empty, or unrecognised THE SYSTEM
  SHALL answer `off`, SHALL print a `warn:`-style line for an unrecognised
  value, and SHALL NOT raise — mirroring
  `orchestrator/lifecycle/rollout.py:62-79`.
- WHILE the mode is `off` THE SYSTEM SHALL accept and validate the new flags
  and signal payloads but SHALL NOT call the work-item store and SHALL produce
  exactly today's investigator behaviour.
- WHILE the mode is `observe` THE SYSTEM SHALL resolve the `WorkItem`, seal the
  `WorkContextRef` and log the reconstructed canonical state, WHILE the issue
  URL SHALL remain the deciding source of task state.
- WHILE the mode is `enforce` THE SYSTEM SHALL allow the reconstructed
  canonical state to veto a run (for example a work item in a terminal state)
  but SHALL NOT allow it to license a run the issue path would refuse.
- WHILE the mode is `only` THE SYSTEM SHALL treat the `WorkItem` as the sole
  source of canonical task state and `--issue-url` SHALL become optional.
- IF the work-item store is unreachable THEN THE SYSTEM SHALL answer
  `WORK_ITEM_UNKNOWN` as a value rather than raising, and SHALL block a
  mutating step only when `blocks_on_unknown()` is true (mode at least
  `enforce` AND the `WORK_CONTEXT_REQUIRED` break-glass unset/true).

Investigator flags

- WHEN `run_issue_investigator.main()` is invoked with `--work-item-id`,
  `--execution-id`, `--resume-from-execution-id`, `--surface`, `--actor-kind`
  and `--actor-id` THE SYSTEM SHALL parse them, validate them and thread them
  into `investigate()` as keyword-only parameters.
- IF `--resume-from-execution-id` is given without `--work-item-id` THEN THE
  SYSTEM SHALL exit non-zero with a message naming the missing flag.
- IF `--surface` or `--actor-kind` carries a value outside the closed
  vocabulary THEN THE SYSTEM SHALL exit non-zero rather than coercing it.
- IF `--issue-url` is omitted THEN THE SYSTEM SHALL require `--work-item-id`
  and the mode `only`, and SHALL resolve the issue URL from the work item;
  otherwise it SHALL exit non-zero.
- WHEN no new flag is supplied THE SYSTEM SHALL behave byte-for-byte as it does
  today, including `investigate(url, tmp_path)` positional calls made by every
  existing test and by `orchestrator/run_issue_poller.py`.

Canonical-state reconstruction

- WHEN canonical task state is reconstructed THE SYSTEM SHALL derive it only
  from the `WorkItem`'s own structured fields, the gitops proposal artifacts
  (`requirements.md`, `design.md`, `tasks.md`, `.status.yaml`) and prior
  execution digests, and the reconstruction function SHALL expose no parameter
  capable of carrying a conversation transcript.
- WHEN reconstruction runs against a work item whose prior execution produced a
  proposal THE SYSTEM SHALL return a state carrying the service, slug, prior
  execution ids and prior status without reading any surface message log.

Resume signal

- WHEN `DevLoopWorkflow` receives a `resume` signal THE SYSTEM SHALL parse the
  payload defensively and SHALL NOT raise from the handler, mirroring the
  `approve` signal (`dev_loop.py:787-800`).
- WHEN a `resume` signal carries an `execution_id` already recorded on the
  workflow THE SYSTEM SHALL treat it as a no-op and SHALL NOT allocate a new
  execution identity.
- IF a second `resume` carrying a different `execution_id` arrives while one
  resume is already pending THEN THE SYSTEM SHALL reject it, record the
  rejection with a reason, and SHALL NOT fork the work item.
- WHEN an accepted `resume` changes the surface or the actor THE SYSTEM SHALL
  set `_approved` back to `False`, clear `_approver`, and record the
  transition, so the existing `await workflow.wait_condition(lambda:
  self._approved)` (`dev_loop.py:827`) re-arms and approval is re-evaluated by
  the current actor.
- WHILE a resume adds any new workflow command THE SYSTEM SHALL gate it behind
  a new `workflow.patched("work-context-resume")` marker so histories recorded
  before this change still replay, per the convention at
  `dev_loop.py:864-869, 2286-2295`.
- WHEN a `work_context` query is issued against a running or completed
  `DevLoopWorkflow` THE SYSTEM SHALL return the work item id, the current
  execution id and sequence, every recorded `ExecutionRef`, the last surface
  and actor, and every resume rejection — so a trace view can correlate both
  executions to one work item.

## Out of scope

- Telegram, web, or any other surface adapter. This proposal defines what a
  surface must pass; it implements no surface.
- Any UI or trace-view rendering. The `work_context` query and
  `to_log_dict()` fields are the seam; the viewer is #195/#199 work.
- Shared mutable model conversation memory of any kind. Nothing here persists
  or replays messages.
- Cross-surface privilege inheritance. A surface transition explicitly clears
  approval rather than carrying it forward.
- Changes to the investigate `ClusterWorkflowTemplate` (mctlhq/mctl-gitops#1279)
  or to the mctl-api operation registry's allowed parameters
  (mctlhq/mctl-api#335). Both are genuine prerequisites of the *submission*
  path and are tracked in those repositories; no file outside
  `mctlhq/mctl-agents` is touched by this proposal.
- Server-side `WorkItem` storage, revisioning or concurrency control. mctl-api#227
  owns that; this repository only mirrors the contract as a client.
- Persisting sealed snapshots durably (ADR 009 follow-up (b)) and the redaction
  helper (follow-up (c)).

## Open questions

- **Submission-path wiring.** The `investigate_params` dict at
  `dev_loop.py:812-815` is where `work_item_id`/`execution_id` would eventually
  be sent, but the CWFT and the operation registry reject unknown parameters
  until mctlhq/mctl-gitops#1279 and mctlhq/mctl-api#335 land. This proposal
  builds and unit-tests a pure `work_context_params()` helper and merges its
  output into `investigate_params` only when the rollout mode is at least
  `enforce` (default `off`, so nothing is sent in production today). A reviewer
  who reads the boundary note more strictly may prefer the helper to exist with
  no call site at all; that is a one-line change to the merge guard. Proceeding
  with the gated merge because it makes the seam exercisable end-to-end without
  changing any current behaviour.
- **`content_hash` stability.** Adding `work_context` to
  `_content_payload` (`context_snapshot.py:860-882`) changes the canonical JSON
  of every snapshot, including ones with `work_context=None`, exactly as the
  always-present `step: null` key does today. `context_snapshot.py:19-21` states
  the module "is not yet imported by production code, only by tests and fixture
  generation", so the only casualty is the golden fixture
  `tests/fixtures/context/investigator-snapshot.json`. Proceeding with an
  unconditional key plus a re-cut fixture, and recording the alternative
  (omit-when-None to preserve legacy hashes) in design.md.
- **Exact mctl-api route shape.** mctl-api#227 is not readable from this clone.
  The client is written against `/api/v1/work-items/...` by analogy with
  `/api/v1/lifecycle/ownership/...` (`orchestrator/lifecycle/client.py:152-282`),
  with route strings isolated in one module-level table so a rename is a
  one-line change and the tests monkeypatch the transport rather than the URL.
- **Where `execution_sequence` is allocated.** Server-side allocation by
  mctl-api is the correct long-term answer (it is the only party that can see
  a concurrent resume from another surface). Until #227 exposes it, the client
  derives the sequence from `len(work_item.executions)` and the workflow relies
  on its own in-memory dedupe plus Temporal's single-writer guarantee for the
  loop it owns. Recorded as a known simplification, in the spirit of ADR-010's
  own "Known simplification" note about CLI-originated claims acquiring with
  `owner_epoch=0`.
- **Work-item state vocabulary.** The issue's diagram names `waiting` and
  `completed-with-followup`; mctl-api#227 may use different spellings. The
  vocabulary is declared in one frozenset in `contract.py` and an unrecognised
  value classifies as `WORK_ITEM_UNKNOWN`, so a mismatch fails closed and is a
  one-line correction.
