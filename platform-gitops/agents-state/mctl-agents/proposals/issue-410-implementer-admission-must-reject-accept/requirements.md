# Implementer admission must reject accepted proposals whose source issue is closed

## Context

Tier 2 (`orchestrator/run_implementer.py`) selects work with
`find_accepted_proposals()` — every `platform-gitops/agents-state/<service>/proposals/<slug>/.status.yaml`
whose `status` is `accepted` — and then, in `implement_one()`, checks exactly two
things before spending a model attempt: the approval gate (`ref.approval_ok`,
`control.requires_human_approval`, gitops#986 / mctl-agents#349) and the GitHub
result preflight (`_preflight_existing_result()`, which looks only at the
deterministic `feat/agents-<slug>` branch and its PR). Nothing in that path ever
looks at the `source.issue` the investigator wrote into the same file
(`run_issue_investigator.write_status_yaml`, `source: {type: github_issue, repo,
issue, url}`). A proposal whose originating issue was closed weeks ago is
therefore indistinguishable, at admission time, from fresh work.

On 2026-09-19 that cost two model attempts:
`.github/issue-67-feat-roadmap-control-plane-reconcile-epi` (source issue closed
2026-09-16) and
`mctl-telegram/issue-510-add-self-identification-tool-get-my-iden` (source issue
closed 2026-09-06, superseded by `#540`). Both landed in `needs-triage` only
because `run-implementer` happened to exit 1; had either produced a trivial
commit, the implementer would have pushed a branch and opened a PR for work that
was already done or already abandoned. The knowledge needed to refuse both runs
already exists in this repo — `run_shepherd._source_issue_state()` reads exactly
this `source:` block and classifies a closed issue as `source-resolved` /
`source-not-planned` (#276, ADR-005) — but only the reconcile sweep calls it, and
only for proposals that have no PR at all. This proposal moves that knowledge in
front of the model call.

## User stories

- AS the platform operator I WANT the implementer to refuse an accepted proposal
  whose source GitHub issue is already closed SO THAT subscription model quota is
  never spent on work that is done, abandoned, or superseded.
- AS the platform operator I WANT the refusal recorded on the proposal with a
  reason that names the issue and its close reason SO THAT triage does not have
  to reconstruct why the run stopped from Argo step logs.
- AS the platform operator I WANT a closed-as-completed issue's merged,
  superseding pull requests listed in that refusal note SO THAT the common
  "closed but superseded" case (`#510` -> `#540`) is legible without manual
  GitHub archaeology.
- AS the platform operator I WANT an unreadable GitHub to leave the proposal
  `accepted` and untouched SO THAT an API outage never mass-retires a queue.
- AS a DevLoopWorkflow owner I WANT a loop parked at the approval gate on an
  issue that has since been closed to stop before the approve flip SO THAT the
  durable loop ends with a legible reason instead of a red implement step.

## Acceptance criteria (EARS)

- WHEN `implement_one()` evaluates an `accepted` proposal whose `.status.yaml`
  carries a `source` block with `type: github_issue`, a `repo` and an `issue`,
  THE SYSTEM SHALL read that issue's state from GitHub before invoking the
  Claude Agent SDK.
- WHEN the source issue is open THE SYSTEM SHALL proceed exactly as today, with
  no additional status write.
- WHEN the source issue is closed with `state_reason` `completed` or absent THE
  SYSTEM SHALL write `status: needs-triage` with `failure.code: source-resolved`
  and `failure.stage: admission`, SHALL NOT clone the target repo, SHALL NOT
  acquire an execution claim, and SHALL NOT invoke the Claude Agent SDK.
- WHEN the source issue is closed with `state_reason: not_planned` THE SYSTEM
  SHALL behave as above but with `failure.code: source-not-planned`.
- WHEN the admission gate refuses a proposal THE SYSTEM SHALL include, in
  `failure.message` and in the `notes` field, the issue reference, the close
  reason, the close timestamp, and the instruction that reopening the issue (or
  re-publishing the proposal as `proposed`) is the supported way to make it
  runnable again.
- WHEN the source issue is closed as completed and GitHub reports merged pull
  requests that reference it THE SYSTEM SHALL append up to three of those PR
  URLs to the refusal message as supersession evidence.
- WHEN the supersession lookup fails or returns nothing THE SYSTEM SHALL still
  record the refusal, with the evidence sentence omitted.
- IF the proposal's `.status.yaml` has no `source` block, or the block is
  partial (missing `repo` or `issue`), or its `type` is not `github_issue`, THEN
  THE SYSTEM SHALL admit the proposal unchanged — an absent link is not evidence
  of staleness, and incident-responder proposals legitimately carry none.
- IF GitHub cannot be read (transport error, non-2xx, unparseable payload) THEN
  THE SYSTEM SHALL leave the proposal `accepted` and untouched, SHALL skip it for
  this tick with `counts_toward_limit=False`, and SHALL NOT write
  `needs-triage`.
- WHILE `_preflight_existing_result()` reports an existing result for the
  deterministic branch (`open`, `merged`, `closed`, `branch-ready` or its own
  `needs-triage`) THE SYSTEM SHALL keep today's adoption behaviour and SHALL NOT
  apply the source-issue gate, so a merged PR is never re-labelled stale by the
  issue it closed.
- WHILE `--dry-run` is set THE SYSTEM SHALL report the refusal in the run
  summary and SHALL NOT write any `.status.yaml`.
- WHEN a batch run's only outcome is an admission refusal THE SYSTEM SHALL count
  it as a failed result (exit 1), exactly as the existing preflight
  `needs-triage` arm does, and SHALL NOT charge it against `--max-proposals`.
- WHEN `DevLoopWorkflow` resumes after its approval wait THE SYSTEM SHALL check
  the issue's state before running the `mctl-agents-approve` CWFT and, if the
  issue is closed, SHALL end the loop with a recorded skip reason instead of
  submitting the approve or implement steps.
- WHILE replaying a workflow history recorded before this change THE SYSTEM
  SHALL take the legacy branch (no issue check) so no in-flight DevLoop execution
  is wedged by a command mismatch.

## Out of scope

- Any new terminal proposal status (`stale`, `superseded`). ADR-005 is explicit
  that retiring a proposal stays an operator decision and that only `merged` and
  `rejected` survive a reconcile cycle; this proposal makes the reason legible
  and leaves the terminal write to a human.
- Content-level detection that the requested change already exists on `main`
  (keyword/path scan of the target tree). It needs a clone, which is exactly the
  cost admission exists to avoid, and its false-positive mode silently drops real
  work.
- Re-classifying why an attempt produced no commits — that is mctl-agents#364.
- Changing `run_issue_investigator`, which still investigates a CLOSED issue with
  a warning (`run_issue_investigator.py:1706`); admission, not intake, is what
  this issue asks to fix.
- Changing the Tier 3 shepherd's reconcile behaviour or its existing
  `source-resolved` / `source-not-planned` semantics.
- Retroactively sweeping proposals already sitting in `accepted` with closed
  source issues through a one-off job; the next tick that selects each one
  applies the gate.

## Open questions

- Should the refusal use `needs-triage` (chosen here, consistent with #276 and
  ADR-005) or a new `stale` terminal state as the issue suggests as an
  alternative? `needs-triage` is reversible by reconcile if a live PR later turns
  up, and a new terminal state would need matching handling in
  `run_shepherd.reconcile_one` and in the reconcile workflow. Proceeding with
  `needs-triage` plus distinct failure codes.
- Is one failed Argo run per stale proposal acceptable, or should an admission
  refusal get its own non-1 exit code (the way `EXIT_BLOCKED_ONLY` = 45 was
  carved out) so the schedule stays green? Proceeding with exit 1 because the
  proposal leaves the `accepted` queue on the same tick, so it fires exactly
  once.
- Should a closed-as-completed issue whose supersession lookup finds a merged PR
  be projected to `rejected` rather than `needs-triage`? That is a terminal write
  a machine would be making on inferred evidence; deferred, evidence is recorded
  in the note instead.
- The DevLoop pre-approve check adds a GitHub read to every loop resuming from a
  wait. Whether that check also belongs on a timer while the loop is parked
  (cancelling a loop whose issue closes mid-wait) is left for a follow-up.
