# Design: issue-198-feat-governance-human-approval-checkpoin

## Current state

### The checkpoint already reaches `approval_pending` and stops

`orchestrator/policy_checkpoint.py` (638 lines) is the enforcement
boundary described by `docs/adr/014-policy-checkpoint.md`. It is
stdlib-only so the Temporal worker, the pollers and the SDK hooks share
one implementation.

- `ActionRequest` (line 114) describes an action without its payload:
  `action_kind`, `operation`, `target`, `args_digest`, `execution_id`,
  `trace_id`, `actor`, `grants`, `metadata`. `action_digest()` (line 133)
  hashes kind, operation, target, args digest, execution id and actor —
  "the exact identity an approval binds to".
- Verdicts are `ALLOW` / `DENY` / `REQUIRE_APPROVAL` (lines 54-57).
- `Decision` (line 165) carries `verdict`, `code`, `reason`,
  `policy_version`, `rule_id`, `action_digest`, `approval_ref`, and three
  properties: `permitted` (`code in (CODE_ALLOWED, CODE_APPROVED)`),
  `undecided`, and — already named for this issue —
  `awaiting_approval`, whose docstring reads: *"A human decision is pending
  on `approval_ref`: a caller (or the #198 Temporal wait) may wait on it
  and then decide again."*
- `checkpoint(...)` already accepts an `approval_ref` keyword, and
  `ApprovalLookup.redeem()` (line 236) already documents *"With
  `approval_ref`, revalidate that receipt only."*

So the re-entry API for #198 exists and is unused. Nothing constructs the
wait.

### The approval store client is complete

`orchestrator/action_approvals.py` (416 lines) holds the mctl-api client:

- `ActionIntent` (line 93) with fields `execution_id`, `action_kind`,
  `target`, `args_digest`, `policy_rule_id`, `policy_version`,
  `artifact_hash`, `work_item_id`; `intent_hash()` (line 120) reproduces
  mctl-api's Go `IntentHash` byte for byte over
  `mctl-action-intent/v1`.
- `intent_for()` (line 131) builds the intent from an `ActionRequest`,
  putting `action_digest()` in `artifact_hash` so the actor is bound too.
- `idempotency_key(intent, attempt=0)` (line 151) — same intent finds its
  request; a different intent is a different request.
- `ActionApprovalClient` with `create`, `get(approval_id)` and
  `consume(approval_id, presented_hash)` (lines 290-309). `get` is the
  read-only call the poll needs and is already implemented.
- `MctlApiApprovals.redeem()` (line 382) is the whole redemption path: no
  execution id is `APPROVAL_REFUSED`; a receipt whose `intent_hash` differs
  from the freshly computed one is `APPROVAL_MISMATCH` with **no consume**;
  a non-approved state maps through `_outcome`; an expired receipt is
  `APPROVAL_EXPIRED`; only a confirmed `consume` returns
  `APPROVAL_GRANTED` with `reason=f"approved by {rec.decided_by or 'a human'}"`.
- `ApprovalRecord` (line 169) carries `id`, `state`, `intent_hash`,
  `expires_at`, `decided_by` — every field a human-facing surface and the
  audit record need.

The store is off by default: `MCTL_POLICY_APPROVALS` unset / empty /
`none` yields `NO_APPROVALS` and `REQUIRE_APPROVAL` simply blocks.

### Every governed call site treats a refusal as terminal-for-now

`docs/adr/014-policy-checkpoint.md` §5 tabulates the governed sites. The
relevant behaviour today:

- `run_shepherd.merge_pr` (`orchestrator/run_shepherd.py:2565`) runs
  `policy_checkpoint.require(policy_checkpoint.checkpoint(GITHUB_PR_MERGE, ...))`
  immediately before `gh pr merge --merge --delete-branch --match-head-commit <SHA>`;
  its docstring states a refusal is answered `(False, None)`, i.e. `wait`,
  "so the next tick re-evaluates the new head". It also has
  `NEVER_MERGE_SERVICES`, an existing precedent for gating merges on a
  human.
- `run_implementer` exits `EXIT_POLICY_REFUSED` (53) on the review
  follow-up, or hands the proposal back with a `policy_handbacks` tally
  bounded by `IMPLEMENT_MAX_POLICY_HANDBACKS` (3) on undecided.
- `options._PolicyCheckpointHook` denies a gated `mcp__*` tool call.

None of these distinguishes `approval_pending` — a receipt id exists in the
`Decision` and is dropped.

### `WAITING_FOR_APPROVAL` is declared but never projected

`dev_loop.py` L123-134 already defines the phase vocabulary:

```python
RUNNING = "RUNNING"
WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
INPUT_TIMED_OUT = "INPUT_TIMED_OUT"
```

`WAITING_FOR_APPROVAL` merely *names* the `wait_condition(lambda: self._approved)`
call; it is never assigned to any query-visible state, and the
`HumanInputState` docstring notes its `state` is never equal to it. There is
therefore no query today that reports "this loop is parked at approval" —
a caller infers it from Temporal status. By contrast `human_input_state`
(L1623) is a real projection. This proposal gives action approvals the
`human_input_state` treatment, not the current approval treatment.

### Temporal already knows how to park durably

`orchestrator/temporal/workflows/dev_loop.py` parks for *proposal*
approval at lines 2246-2296, and it is the pattern to copy. Under
`workflow.patched("approval-watch")` (mctl-agents#420) it runs a bounded
poll loop:

```python
approval_deadline = workflow.now() + APPROVAL_WAIT_DEADLINE
while workflow.now() < approval_deadline:
    try:
        await workflow.wait_condition(
            lambda: self._approved or self._abandoned,
            timeout=APPROVAL_POLL_INTERVAL,
        )
    except TimeoutError:
        parked_state = await _read_issue_state(issue)
        ...
        continue
    break
else:
    approval_ended = "approval wait expired"
```

with signal handlers `approve` (line 1395) and `abandon` (line 2020),
both of which "must never raise, so parse defensively". This is a
proposal-level gate (`proposed -> accepted`), not an action-level one, and
it is orthogonal to this proposal.

`orchestrator/temporal/activities/` holds thin activities;
`human_input.py` there (`find_human_input_request`, ADR 013) is the
precedent for a small read-only activity backing a park.
`orchestrator/temporal/constants.py` defines `TASK_QUEUE = "mctl-dev-loop"`,
`EXECUTION_TASK_QUEUE`, and the admission queue for implementer submits.

### The boundary that shapes this design

Temporal activities in this repo are thin. The *side effects* happen inside
Argo CWFT pods running `run_implementer.py` / `run_shepherd.py`, submitted
by `submit_and_wait`. The shepherd is not in Temporal at all
(`docs/temporal-flow.md`: Tier 3 stays on cron; ADR-006 phase 6, tracker
#217). So "the workflow parks" cannot mean "one Temporal workflow wraps
every governed action" without first moving the shepherd — which is
explicitly out of scope.

## Proposed solution

One contract, two wait drivers, and an authorization boundary that does not
move.

### 1. `orchestrator/approval_wait.py` — the transport-neutral contract

New stdlib-only module, sibling to `policy_checkpoint.py` and importable
from the worker, the pollers and the CWFT entry points alike.

```python
@dataclass(frozen=True)
class ApprovalTicket:
    approval_ref: str
    intent_hash: str
    expires_at: str          # RFC3339, from ApprovalRecord.expires_at
    action_kind: str         # "github.pull_request.merge"
    operation: str           # "merge"
    target: str              # the PR URL
    policy_rule_id: str
    policy_version: str
    reason: str
    trace_id: str
    execution_id: str
    actor: str
    artifact_ref: str = ""   # head SHA, diff URL, proposal slug
```

- `ticket_from(decision, request, record)` builds it from an
  `awaiting_approval` `Decision` plus the `ApprovalRecord` the lookup saw.
- `to_json()` / `from_json()` — the serialization every driver and every
  future surface uses. This is the "API so approval UI/channels can be
  added later" the issue asks for: a surface renders an `ApprovalTicket`
  and calls mctl-api; it never touches workflow state.
- `WaitOutcome` enum: `APPROVED`, `DENIED`, `EXPIRED`, `MISMATCH`,
  `UNDECIDED`.

To produce a ticket, `MctlApiApprovals.redeem()` must surface the
`ApprovalRecord` it already read on the `APPROVAL_PENDING` path.
`ApprovalOutcome` (`policy_checkpoint.py:228`) gains one optional field —
`record: ApprovalRecord | None = None`, or, to keep `policy_checkpoint`
free of any import from `action_approvals`, two scalar fields
`expires_at: str = ""` and `intent_hash: str = ""`. The second form is
chosen: `policy_checkpoint` currently imports nothing from
`action_approvals` (the dependency runs the other way, `action_approvals`
imports `policy_checkpoint as pc`), and inverting it would be a cycle.
`Decision` gains the same two passthrough fields so a call site can build a
ticket from the decision alone.

### 2. `orchestrator/temporal/activities/action_approvals.py` — the read

One activity, read-only, no side effect:

```python
@activity.defn
async def get_action_approval(approval_ref: str) -> dict[str, str]:
    """GET /action-approvals/{id}. Returns the state, intent hash,
    expires_at and decided_by. Never consumes."""
```

It wraps the existing `ActionApprovalClient.get`. An unreachable store
returns `UNKNOWN`, which the gate treats as "keep waiting", not as a
decision. Registered on the control queue in
`orchestrator/temporal/worker.py`.

### 3. `orchestrator/temporal/approval_gate.py` — the Temporal wait driver

A mixin/helper usable by any workflow, implementing ADR 014 §7 verbatim:

```python
async def await_action_approval(ticket: ApprovalTicket, *, woken) -> WaitOutcome
```

- The workflow stores the ticket in `self._pending_approval` and exposes it
  via `@workflow.query def action_approval_state()`. This is the durable,
  queryable `WAITING_FOR_APPROVAL` state, and it holds no pod: the
  activity that hit the checkpoint already ended.
- `@workflow.signal def action_approval_decided(*args)` — parsed
  defensively like `approve`/`abandon`, accepts only an `approval_ref`
  string, ignores any decision payload, and sets a flag when the ref
  matches the parked one. It is a wake-up, never an approval.
- The loop mirrors dev_loop's `approval-watch` block: bounded
  `wait_condition` with `timeout=ACTION_APPROVAL_POLL_INTERVAL` (new
  constant, 15 minutes per ADR 014 §7), inside a
  `while workflow.now() < deadline` where `deadline` is parsed from
  `ticket.expires_at`. On `TimeoutError` it runs `get_action_approval` and
  continues; on a decisive state it breaks; the `else` arm is
  `EXPIRED`.
- Guarded by `workflow.patched("action-approval-gate")` so in-flight
  histories written before the gate existed never see a new command at this
  position — the same hazard `approval-watch` and `slug-scoped-implement`
  guard against.
- On any wake it re-runs the governed step with `approval_ref` set. The
  gate itself never authorizes: the *activity* re-enters
  `checkpoint(..., approval_ref=...)`, which recomputes the intent from the
  action as it stands now and consumes atomically. The workflow's belief is
  advisory, exactly as ADR 014 §7.4 requires.

### 4. `TickApprovalGate` — the cron wait driver, for the shepherd

The shepherd's tick *is* a poll loop that holds nothing between firings, so
it needs no timer — only durable ticket storage and re-entry.

- `merge_pr` learns one new branch: if the decision `awaiting_approval`, it
  builds the `ApprovalTicket`, persists it, logs
  `APPROVAL_PENDING pr=... ref=...`, and returns `(False, None)` — the same
  `wait` it returns today, so no caller changes.
- Persistence: a new `approval` block in
  `.status.yaml` via `orchestrator/proposal_state.py`, written the way every
  other `.status.yaml` write is — from inside the CWFT, under the
  `mctl-gitops-main-writes` mutex. It carries the serialized ticket plus a
  `denials` counter.
- On the next tick, if a ticket is present for this PR, `merge_pr` calls
  `checkpoint(GITHUB_PR_MERGE, ..., approval_ref=ticket.approval_ref)`.
  Because the merge already binds the head SHA in its arguments (ADR 014
  §5: "an approval for one head never merges another"), a push between
  request and decision yields `approval_intent_mismatch`, the receipt is
  **not** consumed, the stale ticket is cleared, and the next tick opens a
  fresh request for the new head. That is the issue's "approval cannot be
  reused for a materially different action/target", and it falls out of the
  existing binding rather than needing new logic.

### 5. Outcome handling per call site

`approval_lookup_error` stays `undecided` and keeps its existing
classification everywhere (harness/retryable, never the item's failure) —
this proposal changes none of that. New handling is only for the decisive
outcomes:

| Outcome | Shepherd merge | Temporal-hosted step |
|---|---|---|
| `approved` | merge runs once; ticket cleared | step resumes |
| `pending` | `wait`, ticket kept | stay parked |
| `denied` | `wait`, `denials += 1`; at the cap, `needs-triage` with `failure.code: approval-denied` | end step per workflow policy |
| `expired` | ticket cleared; a later tick may open a new request | end step, `ended="approval expired"` |
| `intent_mismatch` | ticket cleared; re-request for the new head | re-request |
| `consumed` | treated as **already merged**: do not re-merge; reconcile PR state | idem |

The `consumed` row is the replay-safety answer. ADR 014 §6 already chose
consume-at-decision-time precisely because "a crash after the consume and
before the effect burns the approval without acting, and it never acts
twice". This proposal keeps that and adds the reconcile: because
`run_shepherd` and `orchestrator/pr_adoption.py` already re-read canonical
GitHub PR state, a `consumed` receipt is resolved by asking GitHub whether
the merge landed, not by guessing.

### 6. Record

Two records exist today and both are extended rather than replaced.

`policy_checkpoint.emit()` prints the `POLICY_DECISION <json>` line
(`DECISION_PREFIX`) and *also* calls
`tracing.record_policy_decision(...)`. Contrary to ADR 014 §4's note that
"#195's trace does not exist yet", `orchestrator/tracing.py` has since
landed with `POLICY_DECISION_EVENT = "mctl.policy.decision"` carrying
`mctl.policy.rule_id`, `.decision`, `.code`, `.version`, `.action_kind`,
`.operation`. ADR 015 should correct that sentence.

- **The span event.** `record_policy_decision` gains `approval_ref`,
  `approver` and `decided_at`, emitted as `mctl.policy.approval_ref`,
  `mctl.approval.approver` and `mctl.approval.decided_at`. Note that
  `orchestrator/tracing_sdk.py`'s `GuardedExporter` redacts by key regex
  (`_ALLOWED_KEY` / `_DENIED_KEY`), so the new keys must be added to the
  allow-list or they will be silently dropped — a test must pin this.
  `redeem()` already holds the `ApprovalRecord` with `decided_by`.
- **The stdout record.** `decision_record()` gains the same three fields.
  Still no raw arguments.
- **Two new structured lines**, `APPROVAL_PARKED` and `APPROVAL_RESUMED`,
  carrying `trace_id`, `approval_ref` and the action summary, so
  time-to-decision is derivable. Both follow the `lifecycle/claim.py`
  `_emit` convention ADR 014 §4 pins.

The approver is `ApprovalRecord.decided_by` as mctl-api recorded it. This
is a materially stronger identity than the proposal-level `approve`
signal's `approver` string, which `dev_loop.approve` accepts from any
signaller as unverified free text — a distinction ADR 015 should state
plainly.

### 7. Rollout

Nothing changes by default. The gate is reachable only when
`MCTL_POLICY_APPROVALS=mctl-api` **and** a rule's verdict is
`REQUIRE_APPROVAL`. The built-in policy keeps every current verdict,
including `merge: ALLOW`. Enabling the first governed path is then a policy
change, not a code change — exactly what ADR 014 §"Open decisions" item 3
says: "whether to gate the merge or the push behind REQUIRE_APPROVAL is a
policy change, not a code change."

A new ADR, `docs/adr/015-human-approval-checkpoints.md`, supersedes ADR 014
§7's "design only" status and records the two-driver decision.

## Alternatives

**1. One Temporal workflow wrapping every governed action.** The purest
reading of "Temporal is the orchestration/state boundary": every governed
side effect becomes an activity of an `ApprovalGatedActionWorkflow`.
Dropped because the shepherd is not in Temporal (`docs/temporal-flow.md`
boundaries; ADR-006 phase 6, tracker #217), and the implementer's mutations
happen inside an Argo pod that Temporal only submits to. Adopting this
would mean moving Tier 3 into Temporal first — a much larger change that
#198 does not ask for, and one that would block the issue's own initial
candidate (merge) behind it.

**2. Trust the Temporal signal payload as the approval.** Let mctl-api
signal `approve(approval_ref, decision, approver)` and have the workflow
act on it directly, skipping the re-check. Dropped because it makes
Temporal history an authorization record, which ADR 014 §6 explicitly
rejects: "mctl-api is the durable approval authority; Temporal is only the
wait/resume mechanism, and its state is never the approval record." It also
breaks the binding guarantee — a signal cannot know whether the PR's head
SHA moved since the request — and it would let anyone able to signal the
workflow authorize a merge.

**3. No durable ticket; re-derive the receipt by idempotency key each
tick.** Since `idempotency_key(intent)` is deterministic, a tick could
recompute the intent and re-issue find-or-create, getting the same request
back. Dropped as the primary mechanism because it makes the parked state
invisible — an operator reading `.status.yaml` would see an ordinary
`wait` with no indication a human is blocking it — and because a find-or-
create is a write call on mctl-api's budget every tick rather than a read.
It is kept as the *recovery* path: if a ticket is lost, the next tick
re-derives the same request rather than opening a second one. This is
open question 1 in requirements.md.

**4. Hold the pod and block on a long poll.** Simplest to write: the
activity loops until decided. Dropped outright — it violates the issue's
first acceptance criterion, and the repo has already been burned by exactly
this shape: `docs/temporal-flow.md` records nine approvals reaching Argo at
once in September 2026 and six dying of their own deadline while queued on
a capacity-1 mutex. A human decision takes hours; an Argo deadline does
not.

## Platform impact

**Migrations.** One additive `approval` block in `.status.yaml`. Readers
must tolerate its absence, which `proposal_state.py` already does for
optional blocks. No schema version bump; no backfill. Temporal histories
are protected by `workflow.patched("action-approval-gate")`, so in-flight
loops replay unchanged.

**Backward compatibility.** Default-off twice over: the store must be
enabled *and* a rule must be flipped. With `MCTL_POLICY_APPROVALS` unset,
not one code path in this proposal executes — `redeem()` is never called,
no ticket is ever built, no gate is entered. `merge_pr`'s signature and its
`(False, None)` refusal contract are unchanged, so every existing caller
and test is unaffected.

**Resource impact.** A parked action holds nothing. The added load is one
read per poll interval per parked action: at a 15-minute cadence and a 24h
TTL, at most 96 `GET /action-approvals/{id}` calls per parked action, on
mctl-api's read budget. The shepherd driver adds zero extra polling — it
reuses the tick that already runs. Against this, the gate *saves* the
repeated paid model turns that `EXIT_POLICY_REFUSED` currently causes, since
a parked action no longer re-runs the implementer every tick to be refused
again.

**Risks and mitigations.**

- *A parked action never resumes because the signal was lost and the poll
  is misconfigured.* Mitigated by the deadline: the loop's `else` arm
  always fires at `expires_at`, and the TTL is capped by mctl-api at 7
  days. Fail-closed is the default direction.
- *An approval is burned without the effect running* (crash between consume
  and side effect). Accepted deliberately, as ADR 014 §6 does: it is the
  safe failure. Mitigated for the merge path by reconciling against
  canonical GitHub PR state, which `pr_adoption.py` already does, so a
  merge that actually landed is recognized rather than re-attempted.
- *Denial loops.* A denied receipt answers `approval_denied` forever for
  that intent, so a naive tick would re-ask every 5 minutes. Mitigated by
  the `denials` counter and a terminal `needs-triage`, mirroring the
  existing `policy_handbacks` / `IMPLEMENT_MAX_POLICY_HANDBACKS` bound.
- *Operator confusion between the two approvals.* The proposal-level
  `approve` signal (`proposed -> accepted`) and the new action-level
  approval are different things at different layers. Mitigated by disjoint
  naming throughout — `action_approval_decided`, `ApprovalTicket`,
  `ACTION_APPROVAL_POLL_INTERVAL`, `APPROVAL_PARKED` — and by an explicit
  section in ADR 015.
- *A gated merge stalls the release train.* Mitigated by keeping the merge
  rule at `ALLOW` in the built-in policy and enabling it per-service via
  configuration, so the blast radius of the first flip is one service.
