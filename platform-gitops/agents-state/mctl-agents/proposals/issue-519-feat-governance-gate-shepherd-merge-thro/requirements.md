# Gate the shepherd's merge through the existing Temporal action-approval workflow

## Context

`orchestrator/policy_checkpoint.py` already models a human approval as a
single-use receipt bound to one action of one execution
(`ActionRequest.action_digest`, `MctlApiApprovals.redeem` in
`orchestrator/action_approvals.py`), and
`orchestrator/temporal/workflows/action_approval.py` already provides the
durable wait (`run_gated_action`, `ActionApprovalWaitWorkflow`) plus the
gated-activity contract (`run_gated`, `GatedActionInput`,
`GatedActionResult` in `orchestrator/temporal/activities/action_approval.py`).
Both are registered on the worker (`orchestrator/temporal/worker.py:566,578`)
and have **no production caller**: ADR-014 §7 lists "a first step that adopts
`run_gated_action`" under *Not built*, and its open decision 3 says gating the
merge behind `REQUIRE_APPROVAL` is "a policy change, not a code change".

PR #484 tried to gate the merge from inside the shepherd pod instead, by
persisting an `ApprovalTicket` into `.status.yaml` and resuming it on a later
cron tick. That cannot work: an approval intent contains `execution_id`
(`action_approvals.ActionIntent`), and each shepherd tick runs in a new Argo
pod with a new sealed execution context, so tick N+1 can never redeem tick N's
receipt — it can only create yet another pending request. This proposal drops
that architecture and makes the shepherd's merge the first adopter of the
Temporal primitives: the merge side effect moves into a gated Temporal
activity owned by `DevLoopWorkflow`, whose single durable execution spans the
whole human wait, and the shepherd pod stops merging for gated services.

## User stories

- AS a platform operator I WANT the agent merge of an `feat/agents-*` PR to
  require an explicit human approval of that exact PR and head SHA SO THAT no
  agent-authored code reaches a protected default branch without a named
  human decision.
- AS a platform operator I WANT the approval to be redeemable by the same
  execution that asked for it SO THAT an approval given ten minutes or ten
  hours later is actually usable and no pending request is ever orphaned.
- AS an auditor I WANT the approver identity, the decision and its timestamp
  on the existing `POLICY_DECISION` record and the `mctl.policy.decision`
  span event SO THAT "who let this merge happen" is answerable from the trace
  already collected.
- AS a platform engineer I WANT this off by default and per-service
  opt-in SO THAT enabling governance for one service cannot stop merges
  everywhere else.
- AS a reviewer of #484 I WANT no approval state in `.status.yaml` and no
  second approval store or wait workflow SO THAT there is exactly one
  authority (mctl-api) and one wait mechanism (Temporal).

## Acceptance criteria (EARS)

Policy

- WHEN `MCTL_POLICY_MERGE_APPROVAL` is unset, empty or `none` THE SYSTEM
  SHALL evaluate `github.pull_request.merge` under the unchanged
  `BUILTIN_POLICY` rule `github-pr-merge` (`ALLOW`), and the shepherd's merge
  behaviour SHALL be byte-for-byte what it is today.
- WHEN `MCTL_POLICY_MERGE_APPROVAL=require` THE SYSTEM SHALL evaluate
  `github.pull_request.merge` under a `REQUIRE_APPROVAL` rule carrying its own
  policy version, and SHALL record that version in every decision record.
- IF `MCTL_POLICY_MERGE_APPROVAL` holds any other value THEN THE SYSTEM SHALL
  treat it as a misconfiguration and refuse every merge (fail closed), never
  fall back to `ALLOW`.

The shepherd pod

- WHILE a service is listed in `SHEPHERD_MERGE_APPROVAL_SERVICES` THE SYSTEM
  SHALL NOT invoke `gh pr merge` from a shepherd tick, and SHALL NOT create,
  read, consume or persist any action-approval receipt from that tick.
- WHEN `decide()` would return `merge` for a gated service THE SYSTEM SHALL
  return `defer-merge`, record `merge_owner: devloop-workflow` as descriptive
  routing metadata only, print one greppable `MERGE_GATED` line carrying the
  repo, PR number and head SHA, and leave `.status.yaml`'s `status` unchanged.
- THE SYSTEM SHALL NOT write any approval receipt, ticket, attempt counter or
  denial counter into `.status.yaml`.
- WHILE a service is not gated THE SYSTEM SHALL keep merging exactly as today,
  including the `NEVER_MERGE_SERVICES` refusal and the
  `--match-head-commit` invocation.

The gated merge

- WHEN `DevLoopWorkflow`'s merge watch observes its implementation PR still
  open THE SYSTEM SHALL run the merge attempt through
  `run_gated_action("merge_pull_request_gated", ...)` behind a
  `workflow.patched("gated-merge")` marker, so no pre-existing workflow
  history replays a command it never recorded.
- WHILE the merge gate is disabled for the service THE SYSTEM SHALL answer the
  gated activity with a precondition-unmet result before performing any GitHub
  read, so the poll costs nothing.
- WHEN the gated activity runs THE SYSTEM SHALL recompute, from GitHub in that
  same call, the PR snapshot, the codex review and the required-check status,
  and SHALL request or redeem an approval only when the shepherd's own pure
  `run_shepherd.decide()` returns `merge` for that freshly read state.
- THE SYSTEM SHALL put the exact repository, PR number and observed head SHA
  into the action's arguments, so the approved intent names one head commit
  and no other.
- IF the PR is already merged, closed, draft, or its head SHA differs from the
  head the caller asked about THEN THE SYSTEM SHALL return a precondition-unmet
  result without creating, redeeming or consuming any receipt.
- IF the PR's repository is in `run_shepherd.NEVER_MERGE_SERVICES` THEN THE
  SYSTEM SHALL refuse before the checkpoint, so no human is ever asked to
  approve a merge the code forbids.
- WHEN the checkpoint answers `approval_pending` THE SYSTEM SHALL end the
  activity, holding no pod, and wait in `ActionApprovalWaitWorkflow` keyed by
  the receipt id.
- WHEN a human approves THE SYSTEM SHALL re-run the same gated activity with
  `approval_ref` set, revalidate the intent against the world as it is at that
  moment, consume the receipt, and only then perform the merge.
- WHILE one receipt exists for one intent THE SYSTEM SHALL perform at most one
  `gh pr merge`: an activity retry, a worker crash after the consume, a
  workflow replay or a second waiter SHALL end in `consumed`/`already_waiting`
  and never in a second merge.
- IF the human denies, the receipt expires, the wait times out or the intent no
  longer matches THEN THE SYSTEM SHALL leave the PR unmerged, SHALL NOT
  automatically open a new request for the same head, and SHALL keep the merge
  watch running so a new head (a new intent) is asked about afresh.
- IF mctl-api cannot be reached THEN THE SYSTEM SHALL treat it as undecided,
  never as approved, and retry within the wait's own bound.

Identity and evidence

- WHILE one merge gate is in progress THE SYSTEM SHALL use one stable
  `execution_id` for the request and for every revalidation, and SHALL carry
  it across a merge-watch `continue_as_new` hop.
- WHILE a merge-approval wait is in flight THE SYSTEM SHALL NOT hop the merge
  watch via `continue_as_new`.
- WHEN any approval-flow decision is recorded THE SYSTEM SHALL include
  `approval_ref`, the approver identity (`ApprovalRecord.decided_by`) and the
  observation timestamp in the `POLICY_DECISION` log record and in the
  `mctl.policy.decision` span event, and SHALL leave them empty for a decision
  that never reached a human.
- THE SYSTEM SHALL never log an approval payload, a token or the merge
  arguments themselves — only identifiers and digests, as
  `policy_checkpoint.decision_record` already does.

## Out of scope

- The DevLoop merge-watch terminal-status exit (mctl-agents#516).
- Execution evidence persistence (the #199 children): this proposal emits into
  the existing log/trace path and persists nothing new.
- mctl-api changes: the `action_approval_decided` signal from mctl-api and the
  human approval surfaces (UI, Telegram, GitHub) remain unbuilt; the poll
  (`read_action_approval`) alone makes the wait work, at up to `poll_seconds`
  of latency.
- Gating the implementer's push, PR creation, review trigger or CI re-run.
- Merging PRs that no live `DevLoopWorkflow` owns (cron-only proposals,
  incident proposals): for a gated service those simply do not merge, by
  design. See Open questions.
- Anything from PR #484 beyond the approver/timestamp plumbing and the runbook
  text; `orchestrator/approval_ticket.py` and `proposal_state.approval_payload`
  are not carried over.

## Open questions

1. **Cron-only PRs under a gated service.** A gated service whose proposal has
   no live `DevLoopWorkflow` has no Temporal caller, so its PR never merges and
   waits for a human. Interpretation taken: acceptable and fail-closed; the
   rollout enables `SHEPHERD_MERGE_APPROVAL_SERVICES` only for DevLoop-driven
   services, and the `MERGE_GATED` log line makes the held PRs greppable. A
   later slice could give the cron sweep its own thin caller workflow.
2. **Where a human decides.** mctl-api's approval surfaces do not exist yet, so
   in this slice a decision is recorded through mctl-api's action-approval
   routes directly (operator/API), and the wait notices it at its next 15-minute
   poll. Interpretation taken: build against the existing routes; do not add a
   surface here.
3. **Approval TTL.** `MCTL_POLICY_APPROVAL_TTL_S` defaults to 24 h while the
   merge watch runs for days. Interpretation taken: bound the wait by the
   remaining merge-watch budget and let a lapsed receipt be re-asked for the
   next head, rather than inventing a merge-specific TTL.
4. **Policy version and an in-flight receipt.** Flipping
   `MCTL_POLICY_MERGE_APPROVAL` mid-wait changes `policy_version`, so a pending
   receipt becomes `approval_intent_mismatch`. Interpretation taken: that is
   the correct fail-closed outcome; it is documented in the runbook rather than
   worked around.
