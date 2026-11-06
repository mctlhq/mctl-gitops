# DevLoop Part M, slice M2a: extend M1 state and prepare the guarded dispatcher contract (#993 execution slice)

## Context

Issue #1006 is an execution slice of the approved #993 architecture (umbrella digest
`sha256:1e461962bc774bc5ed7f129c6a78378720a79beb97e601d2ca26985d3109742b`, recorded as provenance only).
It grants no approval to implement. The #993 DevLoop failed (`no-commits`) and is not restarted or recovered,
and its `.status.yaml` is left as it is. M1 (#998, merged) already ships several things. `ResumeDelivery`
carries the defaulted request identity (`intent_id`, `expected_state_version`, `resumed_from_execution_id`),
and `Dispatcher._dispatch` propagates it. M1 also ships the `DEFERRED_RESUME_PATCH` marker, the carried
`deferred_resume_contract`, the ordered post-gates validator in `DevLoopWorkflow._validate_execution_request`,
and the canonical refusal names `work_merged` / `no_actionable_intent`. The legacy read-side aliases
`work-merged` / `nothing-to-resume` are also already there.

M2a adds only the pieces that are still missing and safe on their own:

- test-first coverage of the T1-T4, T2b and T9b invariants, with mutation checks, replay and old-payload checks;
- the defaulted `_feedback_done` and `_pending_feedback` loop state, carried across continue-as-new;
- the tri-state PR, branch and gates reads, plus the pure closed-loop decision that tasks 4 and 4b need. None of
  this is wired into the live dispatch path;
- a read-only `contract_state` query and a `contract-drain-check` CLI;
- an investigation of the `WorkItemClient` read that lists a work item's execution requests. This read is
  implemented only if a supported mctl-api contract exists.

The complete accept path stays disabled. Every M1 fail-closed deferral (`feedback-not-ready`,
`recovery-not-ready`, `legacy-loop`, `implement-running`) stays in force.

This matters because the dispatcher is live in production. `EXECUTION_REQUEST_DISPATCHER: "true"` is set in
`platform-gitops/services/admins/mctl-agents-worker/values.yaml`, image tag `1.117.0`. Any change that alters
how a claimed request is decided reaches users as soon as it is released. M2a must therefore change no
production decision. It may only add state, tests, read primitives and read-only surfaces, so that later slices
can change behaviour behind a reviewed gate.

## User stories

- AS a DevLoop maintainer I WANT the feedback-dedupe state (`_feedback_done`, `_pending_feedback`) to exist,
  default to empty and survive continue-as-new SO THAT the later feedback tick (#993 task 6) can rely on it
  without its own replay migration.
- AS a dispatcher maintainer I WANT tri-state PR, branch and gates reads and one pure closed-loop decision
  function SO THAT task 4b can be wired later without ever treating a failed read as "no PR" or "safe".
- AS an operator I WANT a read-only `contract_state` query and a `contract-drain-check` command SO THAT I can see
  which running loops are legacy, contract or unobservable before any switch is turned on.
- AS a reviewer I WANT every M2a behaviour proven by tests that fail when the change is reverted, and by replay
  of every recorded history, SO THAT the slice adds no replay incompatibility and no silent `Succeeded`.
- AS the #993 owner I WANT every part of tasks 4 and 4b that M2a does not finish to be listed explicitly, with
  its owning slice or dependency SO THAT nothing is marked complete by accident.

## Acceptance criteria (EARS)

Request identity and propagation (verification of M1, T1)

- WHEN a `ResumeDelivery` payload recorded before M1 is decoded through Temporal's default payload converter
  THE SYSTEM SHALL produce `intent_id=None`, `expected_state_version=0`, `resumed_from_execution_id=""`.
- WHEN the dispatcher delivers a claimed request THE SYSTEM SHALL copy `intent_id`, `expected_state_version`
  and `resumed_from_execution_id` from the request into the `ResumeDelivery` unchanged. A test SHALL assert
  each field separately, so that dropping any one field fails it.
- IF M2a finds an identity field or a propagation step that M1 does not already provide THEN THE SYSTEM SHALL
  add only that piece. M2a SHALL NOT redefine fields that M1 already ships.

Feedback state (task 3)

- THE SYSTEM SHALL hold `_feedback_done` (a set of execution request ids) and `_pending_feedback` (an ordered
  tuple of execution request ids) on `DevLoopWorkflow`, both empty after `__init__`.
- THE SYSTEM SHALL carry them in two new defaulted `MergeWatchResume` fields: `feedback_done` (a sorted tuple)
  and `pending_feedback` (in acceptance order). The fold SHALL happen in `_carry_work_context` and the
  restore in `_rehydrate_work_context`.
- WHEN a `MergeWatchResume` recorded before M2a, without these fields, is decoded THE SYSTEM SHALL decode both
  as empty, and the loop's `deferred_resume_contract` SHALL be unchanged.
- WHILE no feedback tick exists (all of M2a) THE SYSTEM SHALL NOT add to either set. No code path in M2a writes
  to them except the carry and restore.
- THE SYSTEM SHALL evaluate `workflow.patched(DEFERRED_RESUME_PATCH)` only at the existing gates-passed site in
  `run` (`dev_loop.py` around line 4299). A continued run SHALL take the value from
  `MergeWatchResume.deferred_resume_contract` and SHALL NOT re-evaluate it.
- WHEN any history in `tests/fixtures/histories/` is replayed THE SYSTEM SHALL replay without non-determinism.
  This includes `dev_loop_deferred_resume.json` and the pre-marker fixtures.

Validator and deferrals (task 4, the non-activating part; T2, T3, T4)

- WHILE M2a is deployed THE SYSTEM SHALL keep `_validate_execution_request`'s M1 order and outcomes unchanged:
  `work_merged` refused, then `legacy-loop` deferred, then `implement-running` deferred, then
  `no_actionable_intent` refused, then `recovery-not-ready` deferred, then `feedback-not-ready` deferred.
- WHEN a resume is refused (`work_merged` or `no_actionable_intent`) THE SYSTEM SHALL reject the request with
  `resume_refused:<reason>` before any fulfil, mint no `we_`, and leave the request row's `intent_id`, surface
  and requester as they were. A redelivery of the same request SHALL produce the same outcome.
- IF a loop recorded without `DEFERRED_RESUME_PATCH` has passed its gates THEN THE SYSTEM SHALL defer a resume
  with `legacy-loop`. Nothing SHALL end `Succeeded`, and `contract-drain-check` SHALL list that loop as legacy.
- IF `_deliver` ever reaches a delivery with `accepted_after_gates=True` THEN THE SYSTEM SHALL land it `Failed`
  with `feedback-not-ready`. This is M1's defence in depth, kept.

Refusal vocabulary (T9b)

- THE SYSTEM SHALL mint only `work_merged` and `no_actionable_intent`. It SHALL NOT mint the hyphenated legacy
  spellings in `dev_loop.py`, `dispatcher.py` or any new M2a module.
- WHEN a stored `resume_refused:work-merged` or `resume_refused:nothing-to-resume` is read, or a Temporal
  `ResumeRefused` error carries one, THE SYSTEM SHALL keep the spelling exactly as written and SHALL NOT rewrite
  it.

Dispatcher and validator contract preparation (tasks 4 and 4b, the safe portions; T2b)

- THE SYSTEM SHALL provide tri-state reads:
  - PR-by-branch for `feat/agents-<slug>`: `open`, `merged`, `closed`, `absent` or `unknown`;
  - branch existence: `exists`, `absent` or `unknown`;
  - gates-passed for a closed loop: `passed`, `not-passed` or `unknown`.
- IF any read fails (transport error, timeout, non-2xx other than a proven absence, an unparsable body, a
  missing token) THEN THE SYSTEM SHALL answer `unknown`. A failed read SHALL never answer `absent`.
- IF GitHub answers 404 on a branch read THEN THE SYSTEM SHALL answer `absent` only when a read of the
  repository itself succeeded in the same call. Otherwise it SHALL answer `unknown`, because GitHub answers an
  unauthorised lookup and a missing one the same way.
- THE SYSTEM SHALL provide one pure function, `closed_loop_decision(...)`, that maps a closed or absent loop
  plus the reads to exactly one outcome:
  - `refuse:work_merged`;
  - `refuse:no_actionable_intent`;
  - `defer:closed-loop-unobserved`;
  - `pass` (proceed as today).
  Any `unknown` input that could change the outcome SHALL yield `defer`.
- WHILE M2a is deployed THE SYSTEM SHALL NOT call these reads or this function from `Dispatcher._dispatch`. The
  construction sites in `worker.py` (around line 936) and `cli.py` (around line 157) stay unchanged, and every
  dispatch decision stays the same as before M2a.
- THE SYSTEM SHALL add `closed-loop-unobserved` to the dispatcher's audited deferral vocabulary
  (`DEFERRAL_AUDITED`). It SHALL NOT add it to the loop's `RESUME_DEFERRAL_REASONS`, because the loop never
  raises it.

Read-only observability (task 4)

- THE SYSTEM SHALL expose a `contract_state` workflow query. It returns:
  - the contract flag, `gates_passed` and `initialized`;
  - the implement stage and outcome;
  - the last PR state, or `unknown` when none was observed;
  - the open delivery ids, `pending_feedback` and `feedback_done`.
  It SHALL schedule no command.
- WHEN an operator runs `python -m orchestrator.temporal.cli contract-drain-check` THE SYSTEM SHALL list the
  running DevLoop workflows and classify each one as `contract`, `legacy`, `pre-gates` or `UNKNOWN` (query
  failed or not supported by the worker). It SHALL print the counts, write nothing, signal nothing, and exit
  non-zero when any loop is `UNKNOWN` or the listing failed.

Execution-request list read (task 4b dependency)

- WHERE mctl-api serves a documented, complete, service-principal-readable list of one work item's execution
  requests THE SYSTEM SHALL add `WorkItemClient.list_execution_requests(work_item_id)`. It returns
  `request-found` only for a complete and fully parsed list, and `request-unknown` otherwise.
- IF that contract cannot be confirmed (the route, the envelope, pagination or completeness, or access for the
  dispatcher's principal) THEN THE SYSTEM SHALL NOT add the read. It SHALL record the exact missing dependency
  in the PR body and in `docs/temporal-flow.md`, and leave the dependent test as a strict expected failure.

Global invariants

- THE SYSTEM SHALL never end a delivery `Succeeded` on a path M2a touches. Unknown SHALL never mean absent or
  safe.
- THE SYSTEM SHALL keep every relevant feature flag OFF and add no new switch that defaults ON.
- WHEN a test covers behaviour owned by a later slice THE SYSTEM SHALL mark it
  `pytest.mark.xfail(strict=True, reason="<owning slice / issue>")` and list it in the PR body. It SHALL never
  be marked complete.

## Out of scope

- Turning on the task 4 accept path (replacing `feedback-not-ready` / `recovery-not-ready` with acceptance).
- Wiring the closed-loop decision into `Dispatcher._dispatch` (task 4b activation); that is M2c.
- Task 4b's execution-request list read, if its backend dependency is missing.
- The feedback tick, `read_rollout_switches`, `run_shepherd --feedback-intent` and the GitOps shepherd CWFT
  change (tasks 5-8).
- Guarded reinvestigation and rewind (task 9), the orphan sweep (tasks 10-11), the `rollout-status` command
  (task 15) and the ADR and runbook (tasks 13 and 16).
- Part S and PR #992.
- Any production flag, release, deployment or merge. #1003 stays Draft and the release hold stays ON.
- Editing #993's `.status.yaml` or proposal, or any other repository.

## Open questions

- Does mctl-api expose a supported list of execution requests per work item, and what is its contract (route,
  envelope, pagination and completeness, service-principal access)? The MCP tool
  `mctl_list_work_item_execution_requests` describes "execution requests made for one WorkItem", which
  suggests a backend list exists. This repo pins no route or schema for it: `WorkItemClient.ROUTES` has only
  the single-request `execution_request` route. The implementer must confirm the contract from mctl-api's
  source before adding the read. If it cannot be confirmed, the read is skipped and the dependency is recorded.
- Slice naming: the issue names M2c for the deferred parts of tasks 4 and 4b, and #1005 (M3) for recovery. This
  proposal assigns the feedback tick (tasks 5-8) to "the slice that owns tasks 5-8" and wiring plus the accept
  path to M2c. The owner should confirm the mapping used in the xfail reasons.
- How should a closed loop's gates-passed state be read? The proposal status in `.status.yaml` (`accepted` or
  later), the last `implement_execution` query on the closed run, or both? M2a implements a tri-state read
  from `.status.yaml` (anything outside a known list is `unknown`). M2c must confirm that it is enough.
- Forward compatibility during rollout: an old worker could receive a `MergeWatchResume` with the new fields.
  M2a adds a test that documents whether Temporal's dataclass converter ignores unknown keys. If it does not,
  the rollout note must require draining hops before a rollback.
