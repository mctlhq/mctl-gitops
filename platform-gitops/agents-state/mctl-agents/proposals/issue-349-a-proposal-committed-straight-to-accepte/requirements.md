# Make a permanently unapprovable proposal fail loudly instead of silently

## Context

A proposal that lands in `agents-state` already at `status: accepted` while
carrying `control.requires_human_approval: true` and no `approval` block cannot
be run by any supported path. `human_approval_satisfied()`
(`orchestrator/proposal_state.py:60-112`) correctly refuses it — `accepted`
alone is not authorisation, which is the hole gitops#986 closed — and the
`mctl-agents-approve` operation (the CWFT lives in mctl-gitops) only performs
the `proposed -> accepted` flip, so on an already-accepted proposal it
short-circuits without writing an approver. Neither side fails. Both report
success. The proposal never moves.

The expensive half of this is not the deadlock itself but its invisibility. The
implementer's refusal is an `ImplementResult.skipped_reason`
(`orchestrator/run_implementer.py:1166-1176`), which `_batch_outcome()` counts
as an ordinary skip and `main()` exits `0` on. From the outside, a run that
skipped everything is byte-for-byte indistinguishable from a run that did work:
same phase markers, same exit code, same `nothing to commit` tail. An operator
watching workflow status has no signal at all, and the skip message itself
points at the dev-loop approve endpoint — a path that does not exist for a
proposal authored outside the Temporal loop. This proposal makes the refusal a
visible, durable, correctly-explained outcome inside mctl-agents, and refuses to
create the unrunnable combination in the first place. Recording an approver on
an already-accepted proposal is a change to `cwft-mctl-agents-approve.yaml` in
mctl-gitops and is explicitly out of scope here.

## User stories

- AS a platform operator I WANT an implement run that could not run anything
  because a proposal is permanently blocked to end non-green SO THAT I learn
  about it from workflow status instead of by reading Argo step logs.
- AS a platform operator I WANT the blocked state recorded in the proposal's own
  `.status.yaml` SO THAT the condition is visible in gitops and survives the
  workflow's log retention.
- AS a platform operator I WANT the refusal message to name a remedy that
  actually applies to this proposal SO THAT I am not sent to an endpoint that
  signals a DevLoopWorkflow which never existed.
- AS an agent author I WANT `update_status_file()` to refuse to create an
  `accepted` + `requires_human_approval` + no-approval proposal SO THAT no
  future writer in this repo can mint another unrunnable one.
- AS a reviewer of gitops history I WANT the blocked marker to be written once
  and not rewritten on every tick SO THAT a stuck proposal does not produce a
  commit every half hour.

## Acceptance criteria (EARS)

- WHEN the implementer discovers an `accepted` proposal whose
  `human_approval_satisfied()` is false THE SYSTEM SHALL classify the outcome as
  `blocked` with the stable code `approval-missing`, distinct from both `failed`
  and `skipped`.
- WHEN a run's results contain at least one `blocked` proposal and zero
  successful implementations and zero failures THE SYSTEM SHALL exit with the
  dedicated non-zero code `EXIT_BLOCKED_ONLY` (45).
- IF a run contains both a blocked proposal and at least one proposal that
  produced a PR THEN THE SYSTEM SHALL exit `0`, so the durable `.status.yaml`
  writes the run already made are still handed off to the commit step, while
  still printing the blocked proposal in a dedicated summary section.
- IF a run contains any `error` result THEN THE SYSTEM SHALL exit `1` as it does
  today, because a failure is the louder signal and must not be masked by the
  blocked code.
- WHEN the batch summary is printed THE SYSTEM SHALL report `blocked` as its own
  total alongside `succeeded`, `failed` and `skipped`, and SHALL NOT count a
  blocked proposal in the `skipped` total.
- WHEN the per-proposal progress marker is closed for a blocked proposal THE
  SYSTEM SHALL print `Finished: blocked`, not `Finished: skipped`.
- WHEN the implementer blocks a proposal outside `--dry-run` THE SYSTEM SHALL
  write a top-level `blocked` block to that proposal's `.status.yaml` carrying
  `code`, `since`, `message` and `remedy`, while leaving `status: accepted`
  unchanged.
- WHILE a proposal's blocked condition is unchanged THE SYSTEM SHALL leave its
  `.status.yaml` byte-identical on subsequent runs, so a permanently blocked
  proposal produces exactly one gitops commit rather than one per tick.
- WHEN the implementer runs with `--dry-run` THE SYSTEM SHALL report the blocked
  proposal in its summary but SHALL NOT write `.status.yaml` and SHALL NOT
  change its exit code from today's behaviour.
- WHEN a previously blocked proposal later passes the approval gate THE SYSTEM
  SHALL remove the `blocked` block as part of the same write that moves it to
  `in-progress`, or that adopts an existing `open` / `merged` / `closed` result.
- WHEN the implementer refuses a proposal that carries a `source` block of type
  `github_issue` THE SYSTEM SHALL include the derived DevLoop workflow id
  (`workflow_id_for()`, `orchestrator/temporal/issue_ref.py:30-37`) in the
  remedy text.
- IF the refused proposal carries no `github_issue` source block THEN THE SYSTEM
  SHALL state that no DevLoopWorkflow exists for it and SHALL NOT instruct the
  operator to use the dev-loop approve endpoint.
- WHEN any refusal message is emitted THE SYSTEM SHALL state that
  `mctl-agents-approve` is a no-op on an already-accepted proposal, and SHALL
  name re-publishing the proposal in `proposed` status as the supported
  recovery.
- IF `update_status_file()` is asked to write a payload whose resulting status is
  `accepted` and whose `human_approval_satisfied()` is false, AND the payload
  previously on disk was not already in that state, THEN THE SYSTEM SHALL raise
  `UnrunnableProposalError` and leave the file untouched.
- WHILE a proposal on disk is already in the unrunnable state THE SYSTEM SHALL
  permit writes that only annotate it (specifically the `blocked` marker), so
  the guard cannot prevent the diagnosis of state it did not create.
- WHEN the incident-responder writes `status: accepted` with no `control` block
  THE SYSTEM SHALL continue to accept that write unchanged.
- WHEN the implementer runs in `--review-feedback` mode THE SYSTEM SHALL be
  unaffected, because that mode selects `implemented` / `review-fixing`
  proposals and never evaluates the approval gate.

## Out of scope

- Changing `cwft-mctl-agents-approve.yaml` in mctl-gitops so that it records
  `approval.approved_by` on an already-accepted proposal. That is the issue's
  suggested direction (1); it lives in a different repository and must be a
  separate, reviewed change there. Nothing in this proposal forges an approval.
- Changing the mctl-gitops implement CWFT so `commit-and-push` still runs when
  the implement step exits non-zero. See the risk note in `design.md`.
- Unblocking the specific proposal
  `mctl-design/issue-21-docs-license-file-reference-in-readme`. That is a data
  change in mctl-gitops, not a code change here.
- Any outbound notification (Telegram, incident creation) from the implementer
  process. The notify step belongs to the CWFT.
- #289's separate concern: the proposal comment not telling the operator which
  approval path actually ran.
- Surfacing `blocked` in the mentor digest, the shepherd's reconcile decisions,
  or the orphan sweep.

## Open questions

- Whether the mctl-gitops implement CWFT runs its `commit-and-push` step after a
  non-zero implement step. If it does not, the `blocked` marker written during a
  blocked-only run is discarded and only the red workflow survives as a signal —
  still strictly better than today, and self-healing once the CWFT is fixed or
  once a later run does other work. Not verifiable from this repository;
  proceeding with the red-workflow signal as the primary fix and the marker as
  the durable secondary one.
- Whether `EXIT_BLOCKED_ONLY` should also fire when a blocked proposal coexists
  with a successful one. Decided no, because a non-zero exit there risks
  discarding a real `.status.yaml` -> PR handoff; the dedicated summary section
  plus the durable marker carry the signal in that case.
- Whether `blocked` should instead be nested under the existing `failure` block.
  Decided no: `failure` means "an attempt ran and failed", is written only
  alongside `needs-triage`, and is read by the shepherd's
  `SOURCE_RECHECKED_FAILURE_CODES` logic (`orchestrator/run_shepherd.py:291-320`).
  Overloading it would make a never-attempted proposal look like a failed one.
- Whether a future in-repo `record_approval` entry point should exist so the
  gitops CWFT can delegate the "record approver on an already-accepted proposal"
  semantics to this repo instead of reimplementing them in shell. Recorded as a
  follow-up, not built here.
