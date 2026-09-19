# Resume the investigator from a canonical WorkItem across surfaces

## Context

Today a dev-loop run is keyed to one GitHub issue and nothing else.
`orchestrator/temporal/issue_ref.py:30` derives the Temporal workflow id as
`dev-loop-{owner}-{repo}-{issue}`, `orchestrator/temporal/start.py:65` starts
`DevLoopWorkflow` with a single-field input `IssueRef(issue_url)`
(`orchestrator/temporal/workflows/dev_loop.py:370`), and the investigate submit
carries exactly three params — `issue_url`, `agent_image`, `agent_version`
(`dev_loop.py:812-817`). A successful run burns that workflow id forever
(`WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY`, `start.py:70`), and the
only way to touch the issue again is a restart that re-investigates from
scratch — the code says so in its own words: "It is a restart, not a resume —
the new run re-investigates and waits for a fresh approve signal"
(`dev_loop.py:925-935`). There is no actor, no surface, no work-item identity
anywhere on the input or in workflow state; the single human-provenance field
is `self._approver`, set by an unauthenticated `approve` signal
(`dev_loop.py:787-800`, `orchestrator/temporal/cli.py:113-118`).

This proposal adds resume semantics so one durable unit of work — a **WorkItem**,
owned by the mctl-api contract this depends on — can span multiple executions
started from different surfaces, without replaying any original chat transcript.
Each execution stays immutable and gets its own identity and its own
`ContextSnapshot` (`orchestrator/context_snapshot.py`, ADR 009), correlated back
to the same WorkItem, so trace and evidence views can join executions A and B.
Canonical task state is reconstructed from durable artifacts the platform
already owns — the WorkItem record, the proposal triplet under
`platform-gitops/agents-state/<service>/proposals/<slug>/`, and the GitHub issue
— never from a surface conversation log. The pilot is the investigator flow
only; Temporal remains the single durable orchestration engine.

## User stories

- AS a platform operator I WANT to start an investigator execution from a
  canonical WorkItem reference SO THAT the run is identified by the unit of
  work rather than by whichever surface happened to trigger it.
- AS an operator who began work in one surface I WANT to resume the same
  WorkItem from a second surface SO THAT the loop continues without the first
  surface's transcript and without re-opening a duplicate issue.
- AS an auditor I WANT every execution and every `ContextSnapshot` to remain
  immutable and correlated to one WorkItem SO THAT "what ran, on what input,
  for which unit of work" is answerable after the fact.
- AS a security reviewer I WANT actor/surface transitions recorded as
  identifiers and approval re-evaluated per execution SO THAT no privilege
  granted in surface A is inherited by surface B.
- AS an on-call engineer I WANT concurrent resume attempts to be idempotent or
  explicitly rejected SO THAT two surfaces cannot fork one unit of work into
  two racing agent runs.

## Acceptance criteria (EARS)

- WHEN `run_issue_investigator` is invoked with a canonical work-item reference
  THE SYSTEM SHALL resolve that WorkItem from the mctl-api work-context surface
  and open a new execution against it before any agent invocation.
- WHEN an execution is opened against a WorkItem THE SYSTEM SHALL record an
  execution identity minted by the WorkItem store (execution id plus the
  WorkItem epoch the execution belongs to) and SHALL NOT invent one locally.
- WHEN an investigator execution completes THE SYSTEM SHALL seal exactly one
  root `ContextSnapshot` via `orchestrator.context_snapshot.seal` carrying a
  `work_item` correlation block, and SHALL persist it against that execution.
- WHEN a second execution resumes the same WorkItem from a different surface
  reference THE SYSTEM SHALL create a new execution identity and a new
  `ContextSnapshot`, and SHALL carry the prior execution ids and prior snapshot
  ids as correlation fields on the new snapshot.
- WHILE a resume is in progress THE SYSTEM SHALL treat every previously
  recorded execution record and `ContextSnapshot` as immutable and SHALL NOT
  issue any update or delete against them.
- WHEN a resume is requested THE SYSTEM SHALL reconstruct canonical task state
  from the WorkItem record, the existing proposal directory under
  `agents-state/<service>/proposals/<slug>/`, and the GitHub issue only, and
  SHALL NOT require, request, or accept a raw surface transcript as input.
- WHEN a resume changes the surface or actor relative to the prior execution
  THE SYSTEM SHALL record the transition as `{surface_kind, surface_id,
  actor_kind, actor_id, reason_code}` identifiers at metadata level, and SHALL
  record no conversation content.
- IF a resumed execution reaches the approval gate THEN THE SYSTEM SHALL
  require an approval granted for the current WorkItem epoch, and SHALL NOT
  treat an approval recorded for an earlier epoch as satisfying it.
- WHILE the workflow is parked on `workflow.wait_condition(lambda:
  self._approved)` (`dev_loop.py:827`) THE SYSTEM SHALL accept a resume signal
  that records the actor/surface transition without starting a second Temporal
  execution for the same epoch.
- IF two resume attempts for the same WorkItem carry the same idempotency key
  THEN THE SYSTEM SHALL return the same execution identity to both and SHALL
  start at most one Temporal execution.
- IF a resume attempt presents a stale expected epoch THEN THE SYSTEM SHALL
  reject it with a non-retryable, explicitly-conflicting outcome and SHALL NOT
  start an execution.
- IF the WorkItem store is unreachable or returns an indeterminate answer THEN
  THE SYSTEM SHALL fail the resume closed and SHALL NOT proceed with an
  invented or reused execution identity.
- IF no work-item reference is supplied THEN THE SYSTEM SHALL behave exactly as
  today (issue-keyed workflow id, no work-item block on any snapshot), so the
  existing `agents:intake` poller path is unchanged.
- WHEN a resumed execution targets a proposal whose `.status.yaml` status is
  outside `_OVERWRITABLE_STATUSES` (`run_issue_investigator.py`) THE SYSTEM
  SHALL refuse to overwrite it, report the refusal against the WorkItem, and
  exit without running the agent.
- WHEN a snapshot is exported for traces THE SYSTEM SHALL emit only
  `work_item_id`, `execution_id` and `epoch` alongside the existing
  `to_log_dict()` fields, and SHALL emit no locator, selector, or
  payload-derived string.
- WHILE any resume field exists in the schema THE SYSTEM SHALL contain no
  field whose name encodes an authorization decision (`allow`, `deny`,
  `permit`, `grant`, `authorized`), preserving ADR 009 sec. 5.
- WHEN new branching is added to `DevLoopWorkflow` THE SYSTEM SHALL gate it
  behind a `workflow.patched` marker so histories recorded before this change
  replay unchanged.

## Out of scope

- Telegram, web, or any other surface adapter implementation. This proposal
  consumes surface references; it does not create surfaces.
- UI or trace-view design. Only the correlation fields those views need.
- The mctl-api WorkItem storage model itself (owned by the depended-on
  mctl-api contract). This repository is a client of it.
- Shared mutable model conversation memory, transcript storage, or any form of
  context carried as free text between executions.
- Cross-surface privilege inheritance, and any change to who may approve.
  Authorization enforcement stays with mctl-api and the approval contract.
- Resume for the implementer and shepherd tiers (`run_implementer.py`,
  `run_shepherd.py`). The pilot is the investigator only.
- A second workflow engine, a continue-as-new refactor, or any change to the
  14-day merge-watch cadence budget (`dev_loop.py:129-144`).
- Reconciling the two disagreeing prompt-hash algorithms noted in ADR 009.

## Open questions

- Does an approval granted in epoch N survive into epoch N+1 when the resume is
  a pure surface change by the same actor? This proposal takes the safe
  reading — approvals are epoch-scoped and a resumed execution needs a fresh
  approve — and leaves widening to the approval contract owner.
- Exact mctl-api route shapes and field names for the work-context surface
  (`/api/v1/work-items/...`) are assumed from the dependency and are isolated
  behind one client module so a rename is a one-file change.
- Whether a resume against a still-RUNNING workflow should ever be allowed to
  start a second execution (e.g. the first is wedged). This proposal routes it
  as a signal only; taking over a live run is ADR-010 ownership territory.
- Whether the WorkItem id should be derivable from the issue URL for
  already-running loops, or minted server-side only. This proposal assumes
  server-minted, with the issue URL carried as the WorkItem's canonical task
  reference.
- Whether `mctl-agents-investigate` CWFT parameters may be extended in the
  same release as this change (a sibling-repo gitops edit) or must land one
  release earlier. Sequencing is handled in tasks.md as a separate,
  earlier-landing task.
