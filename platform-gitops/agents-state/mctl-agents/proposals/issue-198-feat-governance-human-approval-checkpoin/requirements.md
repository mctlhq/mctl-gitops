# Human approval checkpoints for high-impact agent actions

## Context

Issue #197 landed the runtime policy checkpoint
(`orchestrator/policy_checkpoint.py`, ADR 014) and the durable single-use
approval store client (`orchestrator/action_approvals.py`, backed by
mctl-api#366). Today a `REQUIRE_APPROVAL` verdict can already be redeemed:
`MctlApiApprovals.redeem()` finds-or-creates an `ActionApprovalRequest`,
and `Decision.awaiting_approval` reports `approval_pending` with the
receipt id. What does not exist is the other half — nothing ever *waits*
for that receipt. Every governed call site treats a non-permitted decision
as a terminal refusal for this attempt: `run_shepherd.merge_pr` answers
`(False, None)`, `run_implementer` exits `EXIT_POLICY_REFUSED` (53) or
hands the proposal back, and the MCP `PreToolUse` hook
(`options._PolicyCheckpointHook`) denies the tool call. ADR 014 §7 sketches
the wait but explicitly leaves it unbuilt, and §"Open decisions" item 1
names it as #198.

This proposal builds that half: a durable `WAITING_FOR_APPROVAL` state that
holds no execution pod, resumes the *exact* blocked action once a human
decides, and records approver, decision and timestamp in the execution
trace. The authorization boundary does not move — mctl-api stays the sole
approval authority and `policy_checkpoint.decide()` stays the sole place an
approval is spent. What is added is a *wait driver* abstraction so a parked
action can be resumed by whichever runtime hosts it, plus the first
end-to-end governed path on a high-impact GitHub mutation.

## User stories

- AS a platform owner I WANT a high-impact agent action (a PR merge) to
  pause for my explicit approval SO THAT an autonomous agent cannot land
  code on `main` without a named human accepting it.
- AS a platform owner I WANT the approval to name the exact action, target,
  head SHA, policy reason and trace id SO THAT I can decide without reading
  the agent's transcript.
- AS a platform owner I WANT an approval I granted for one action to be
  unusable for a materially different one SO THAT an agent cannot retarget
  a granted decision onto another repository, branch or commit.
- AS an SRE I WANT a parked action to consume no pod, no Argo deadline and
  no model quota while it waits SO THAT a slow human decision does not cost
  capacity or produce spurious failures.
- AS an SRE I WANT timeout behaviour to be deterministic and documented SO
  THAT a forgotten approval fails closed instead of parking forever.
- AS an auditor I WANT the approver identity, the decision and its
  timestamp attached to the execution trace SO THAT every governed mutation
  has an accountable human on the record.
- AS a platform engineer I WANT approval surfaces (mctl UI, Telegram,
  GitHub) to be addable later SO THAT workflow semantics are not coupled to
  one frontend.

## Acceptance criteria (EARS)

### Parking

- WHEN `policy_checkpoint.decide()` returns a decision whose
  `awaiting_approval` is true, THE SYSTEM SHALL emit an `ApprovalTicket`
  carrying `approval_ref`, `intent_hash`, `expires_at`, and the
  human-readable action summary (`action_kind`, `operation`, `target`,
  `policy_rule_id`, `reason`, `trace_id`, `execution_id`, `actor`), and
  SHALL NOT perform the side effect.
- WHEN a governed action returns an `ApprovalTicket`, THE SYSTEM SHALL
  record the ticket durably outside the executing process before that
  process exits.
- WHILE an action is parked awaiting approval, THE SYSTEM SHALL hold no
  execution pod, no Argo workflow and no Claude model session attributable
  to that action.
- WHEN a Temporal-hosted action parks, THE SYSTEM SHALL enter a queryable
  `WAITING_FOR_APPROVAL` state exposing the `approval_ref` and the
  `expires_at` it is bounded by.

### Waking and resuming

- WHEN mctl-api records a decision on an approval request, THE SYSTEM SHALL
  accept a best-effort wake-up signal naming only the `approval_ref`.
- IF a wake-up signal carries any decision payload, THEN THE SYSTEM SHALL
  ignore that payload and treat the signal solely as a prompt to re-check
  the store.
- WHILE parked and before `expires_at`, THE SYSTEM SHALL re-read the
  approval state on a bounded poll cadence, so that a lost signal delays
  resumption by at most one poll interval and never loses it.
- WHEN a parked action wakes, THE SYSTEM SHALL re-run the governed action
  with `approval_ref` set, so that `checkpoint(..., approval_ref=...)`
  recomputes the intent from the action as it stands now and revalidates
  that exact receipt.
- WHILE an action is parked, THE SYSTEM SHALL treat its own stored belief
  about the approval state as advisory only, and SHALL authorize the side
  effect solely on a `CODE_APPROVED` decision from the checkpoint.

### Binding and single use

- IF the recomputed intent hash differs from the hash the receipt is bound
  to, THEN THE SYSTEM SHALL refuse with `approval_intent_mismatch`, SHALL
  NOT consume the receipt, and SHALL NOT perform the side effect.
- WHEN an approval is spent, THE SYSTEM SHALL consume it atomically in
  mctl-api before the side effect runs, so that a second attempt on the
  same receipt answers `approval_consumed`.
- IF a retry or Temporal replay re-enters a governed action whose receipt
  is already `consumed`, THEN THE SYSTEM SHALL treat the external mutation
  as already performed and SHALL NOT perform it a second time.

### Outcomes

- WHEN the decision is `approved`, THE SYSTEM SHALL perform the side effect
  exactly once and resume the workflow step that was blocked.
- WHEN the decision is `denied`, THE SYSTEM SHALL terminate or skip the
  blocked action according to that call site's declared policy, and SHALL
  NOT retry the same intent without a new request attempt.
- IF `expires_at` passes with no decision, THEN THE SYSTEM SHALL stop
  waiting, record `approval_expired`, and end the blocked action according
  to that call site's declared policy.
- IF the approval store cannot answer (`approval_lookup_error`), THEN THE
  SYSTEM SHALL classify the attempt as undecided rather than as the item's
  failure, and SHALL retry with backoff while the deadline still runs.
- WHILE `MCTL_POLICY_APPROVALS` is unset, empty or `none`, THE SYSTEM SHALL
  behave exactly as it does today: `REQUIRE_APPROVAL` blocks, nothing
  parks, and no HTTP call is made.

### Record

- WHEN any approval-related decision is reached, THE SYSTEM SHALL emit the
  existing `POLICY_DECISION` record carrying `approval_ref`, decision and
  code, and SHALL NOT include raw action arguments.
- WHEN a receipt is consumed, THE SYSTEM SHALL record the approver identity
  (`ApprovalRecord.decided_by`), the decision and the decision timestamp on
  the execution trace for that `trace_id`.
- WHEN an action parks and when it resumes, THE SYSTEM SHALL emit a
  distinguishable record for each transition so that time-to-decision is
  derivable from the trace.

### First governed path

- WHEN the policy rule for `github.pull_request.merge` is set to
  `REQUIRE_APPROVAL`, THE SYSTEM SHALL park the shepherd's merge of that PR
  rather than merging it, and SHALL merge it on a later tick only after a
  human approves the receipt bound to that exact PR URL and head SHA.
- IF the PR's head SHA changes while a merge approval is pending, THEN THE
  SYSTEM SHALL refuse the pending receipt as an intent mismatch and SHALL
  require a new approval for the new head.

## Out of scope

- Approval user interfaces and notification channels (mctl UI, Telegram,
  GitHub comments). This proposal defines the data the surfaces read and
  the wake-up signal they trigger; building a surface is separate work.
- The mctl-api side of the contract: the `ActionApprovalRequest` resource,
  its decision endpoints and the outbound wake-up signal already exist or
  are tracked under mctl-api#366. Only the client and the wait live here.
- Changing the built-in policy's defaults. Every action stays at its
  current verdict; the merge rule flip is delivered as a configuration
  change, gated behind the feature flag, not as a new default.
- Governing the agent's own `Bash` transport (`gh` / `git` from inside a
  model turn). That remains ADR 014 open decision 4.
- Moving the shepherd into Temporal. That is ADR-006 phase 6, tracker #217.
  This proposal works with the shepherd where it is.
- Approvals for `mcp__*` tool calls inside a live model turn. A model turn
  cannot durably park, so a gated MCP call keeps its current behaviour of
  returning `approval_pending` to the agent as a refusal.
- Multi-party or quorum approval, delegation, and approval policies keyed
  on actor seniority.

## Open questions

1. **Where the merge ticket is persisted for the shepherd.** The shepherd
   is cron-driven and its durable per-proposal state is
   `.status.yaml` (`orchestrator/proposal_state.py`), written only from
   inside an Argo CWFT under the `mctl-gitops-main-writes` mutex. The
   proposal assumes a new `approval` block there. Storing it only in
   mctl-api and re-deriving the receipt by idempotency key each tick is a
   viable alternative that avoids a gitops write; it is recorded in
   design.md as alternative 3. Proceeding with the `.status.yaml` block
   because it makes the parked state visible where operators already look.
2. **Poll cadence for the Temporal gate.** ADR 014 §7 suggests 15 minutes.
   The existing proposal-approval park uses `APPROVAL_POLL_INTERVAL` of 6
   hours. Proceeding with 15 minutes for action approvals, as a gated
   mutation is far more latency-sensitive than a proposal review, and
   making it a named constant so it can be tuned without a code change to
   the gate.
3. **Default TTL for an action approval.** `MCTL_POLICY_APPROVAL_TTL_S`
   defaults to 24h and mctl-api caps at 7 days. Whether a merge approval
   should have a shorter TTL than a generic action approval is unresolved;
   proceeding with the existing 24h default and a per-call-site override
   hook.
4. **Whether a denied merge should be terminal for the proposal.** A denial
   could mean "never merge this" or "not yet". Proceeding with `wait` plus
   a recorded denial and a bounded denial counter, so a human denial does
   not silently strand the proposal but also does not re-ask every tick;
   the terminal interpretation can be added later as a call-site policy.
5. **Trace emission.** ADR 014 §4 notes #195's trace does not exist yet and
   `POLICY_DECISION` follows the structured-log convention instead.
   Proceeding on that convention, with the approver fields shaped as trace
   attributes so #195 can adopt them without a format change.
