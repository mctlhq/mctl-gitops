# Design: issue-519-feat-governance-gate-shepherd-merge-thro

## Current state

**The checkpoint.** `orchestrator/policy_checkpoint.py` decides one action
immediately before its side effect. `BUILTIN_POLICY` (line 311) has
`Rule("github-pr-merge", GITHUB_PR_MERGE, "merge", ALLOW)` with the comment
"a tighter policy (a merge behind REQUIRE_APPROVAL, say) is one rule change,
not a code change". A `REQUIRE_APPROVAL` verdict is permitted only when the
`ApprovalLookup` *spent* a receipt in that same call (`decide()` →
`_redeem()`), and `Decision.permitted` is `code in {allowed, approved}`.
`configured_approvals()` returns `NO_APPROVALS` unless
`MCTL_POLICY_APPROVALS=mctl-api`, in which case `REQUIRE_APPROVAL` refuses with
`approval_required` and nothing is created.

**The approval authority.** `orchestrator/action_approvals.py` reproduces
mctl-api's `IntentHash` byte for byte. `ActionIntent` binds
`execution_id`, `<action_kind>:<operation>`, `target`, `args_digest`,
`policy_rule_id`, `policy_version` and `artifact_hash` (the checkpoint's own
action digest, which covers the actor). `idempotency_key(intent, attempt)` is
deterministic, so re-asking the same intent finds the same request;
`MctlApiApprovals.redeem` (line 404) refuses outright when
`request.execution_id` is empty, compares the stored `intent_hash` with a
freshly recomputed one, and only then calls `consume`.

**The wait.** `orchestrator/temporal/workflows/action_approval.py` provides
`run_gated_action(activity, GatedActionInput)`: it runs the gated activity once;
on `approval_pending` it starts `ActionApprovalWaitWorkflow` as a child keyed
`action-approval-<receipt>` (holding no pod), wakes on the
`action_approval_decided` signal or a 15-minute durable timer, and on every
wake re-runs the *same* activity with `approval_ref` set. Outcomes are returned
as values: `ran`, `denied`, `expired`, `timed_out`, `consumed`, `mismatch`,
`refused`, `blocked`, `effect_failed`, `undecided`, `already_waiting`.
`orchestrator/temporal/activities/action_approval.py` holds the activity side:
`GatedActionInput` (payload + `execution_id`/`actor`/`trace_id`/`attempt`/
`approval_ref`), `GatedActionResult`, and `run_gated()`, whose docstring is
explicit that `args` "must be everything the side effect depends on,
recomputed from the world on every call". Both are registered in
`orchestrator/temporal/worker.py` (`read_action_approval` at :566,
`ActionApprovalWaitWorkflow` at :578). **Nothing in production calls
`run_gated_action` today** — the only caller is
`tests/approval_probe_workflow.py`. ADR-014 §7 says so, and its open decision 3
names the merge gate as a policy change.

**The shepherd.** `orchestrator/run_shepherd.py` is a CLI run in an Argo pod
(`cwft-mctl-agents-shepherd`), either from the `mctl-agents-shepherd` cron or
as `DevLoopWorkflow._shepherd_tick`'s `_run_cwft("mctl-agents-shepherd", ...)`
(dev_loop.py:3714). `decide()` (line 1919) is pure and ends
`return ("defer-merge", None) if fix_only else ("merge", None)` (line 2038);
`merge_pr()` (line 2569) refuses `NEVER_MERGE_SERVICES`, calls
`policy_checkpoint.require(policy_checkpoint.checkpoint(GITHUB_PR_MERGE,
"merge", pr_ref, {"method", "delete_branch", "match_head_commit"}, ...))`,
then runs `gh pr merge --merge --delete-branch --match-head-commit <SHA>`.
A refused or failed merge is surfaced as `wait`, i.e. "nothing to do this
tick". Ownership is per service: `_service_mode()` (line 630) over
`SHEPHERD_SKIP_SERVICES` / `SHEPHERD_FIX_ONLY_SERVICES`, and
`_merge_owner_for()` (line 612) records `pr-steward` or `human-codeowner` as
"descriptive routing metadata, NOT an authorization or readiness signal — see
mctlhq/mctl-agents#344, where a reviewer read the field as a merge
authorization".

**Why #484's design is dead.** Each shepherd tick is a fresh Argo pod with a
fresh sealed execution context (`policy_checkpoint.current_identity()` reads
`MCTL_EXECUTION_CONTEXT_FILE`), so `execution_id` — a field of the intent hash
— changes every tick. #484 therefore had to persist an `ApprovalTicket` into
`.status.yaml` (`orchestrator/approval_ticket.py`, `proposal_state
.approval_payload`, `MERGE_APPROVAL_DENIAL_LIMIT`, `_park_merge_approval`,
`_resolve_parked_merge_refusal`, `_reconcile_consumed_merge`) and still could
not redeem it: the next tick's recomputed intent hash differs, which
`MctlApiApprovals.redeem` answers `mismatch`. The one part of #484 that is
architecture-neutral and worth keeping is the evidence plumbing: `Decision
.approver` / `Decision.decided_at`, `ApprovalOutcome.decided_by`, their
propagation through `_redeem`/`decision_record`/`emit`, and the three extra
kwargs on `tracing.record_policy_decision`. Its ADR/runbook text is reusable
once rewritten for the Temporal flow.

**What the worker can do.** The Temporal worker runs the same image as the
pods (`Dockerfile`, which installs the `gh` CLI at :65) and already resolves a
GitHub token without touching `os.environ`
(`activities/proposals.py::_resolve_token`, used by `activities/pr_state.py`).
Activities already import `run_shepherd` helpers
(`activities/discovery.py:27`, `activities/orphans.py:16`), so the shepherd's
own pure `decide()` and its GitHub readers are reachable from an activity.

## Proposed solution

Four pieces. The authority stays mctl-api, the wait stays
`ActionApprovalWaitWorkflow`, and the only thing that moves is *where the merge
side effect runs*: out of the per-tick Argo pod and into a gated Temporal
activity owned by the one durable execution that can span a human decision.

### 1. A policy variant, selected by env (`orchestrator/policy_checkpoint.py`)

Add, next to `configured_approvals()`:

- `MERGE_APPROVAL_ENV = "MCTL_POLICY_MERGE_APPROVAL"`, value `require`.
- `MERGE_APPROVAL_POLICY`: `BUILTIN_POLICY` with the `github-pr-merge` rule
  replaced by `Rule("github-pr-merge-approval", GITHUB_PR_MERGE, "merge",
  REQUIRE_APPROVAL)` and `version="mctl-agents/policy/v1-merge-approval"`.
  A distinct version is deliberate: `policy_version` is a field of the intent
  hash, so a receipt approved under one rule set can never be spent under the
  other.
- `configured_policy() -> Policy`: `BUILTIN_POLICY` when the env is unset,
  empty or `none`; `MERGE_APPROVAL_POLICY` for `require`; and for any other
  value a policy whose merge rule is `DENY` (fail closed, mirroring
  `_MisconfiguredApprovals`).

Callers that pass `policy=configured_policy()`: the new gated activity and
`run_shepherd.merge_pr`. Everything else keeps `BUILTIN_POLICY`, so no other
governed path changes.

Also carried over from #484 (evidence, not architecture): `Decision.approver`,
`Decision.decided_at`, `ApprovalOutcome.decided_by`, `_redeem` returning them,
`decision_record` emitting them, `emit` forwarding them, and the
`approval_ref`/`approver`/`decided_at` kwargs on
`tracing.record_policy_decision`. `MctlApiApprovals` fills `decided_by` from
`ApprovalRecord.decided_by`. `GatedActionResult` gains the same two fields so
the workflow can log them.

### 2. The gated activity (`orchestrator/temporal/activities/pr_merge.py`, new)

```
@activity.defn
async def merge_pull_request_gated(inp: GatedActionInput) -> GatedActionResult
```

`inp.payload`: `{"repo", "pr_number", "head_sha", "service", "slug"}` —
`head_sha` is the head the caller asked about, not a licence.

Order of work, all of it in `asyncio.to_thread` because the underlying readers
are `gh` subprocesses:

1. **Gate off?** If `configured_policy()` is `BUILTIN_POLICY` or
   `payload["service"]` is not in `SHEPHERD_MERGE_APPROVAL_SERVICES`, return
   `GatedActionResult(code=CODE_MERGE_GATE_DISABLED)` before any network call.
   `outcome_of()` maps an unrecognised code to `blocked`, which the caller
   treats as "nothing to do".
2. **Never-merge repos.** `service in run_shepherd.NEVER_MERGE_SERVICES` →
   `CODE_MERGE_FORBIDDEN`. Before the checkpoint, so no human is ever asked for
   a merge the code refuses anyway.
3. **Recompute the world.** `run_shepherd._fetch_pr_snapshot(repo, number)`,
   then `run_shepherd.read_codex_review(pr)` and
   `ci_checks.read_required_checks(pr)`.
4. **Preconditions** → `CODE_MERGE_PRECONDITION_UNMET` with a typed reason,
   nothing created or consumed: snapshot unreadable; `pr.merged`;
   `pr.closed_unmerged`; `pr.is_draft`; `pr.head_sha != payload["head_sha"]`.
5. **The shepherd's own decision.** `run_shepherd.decide(pr, codex, ci=ci)`
   must return `merge`; anything else (`wait`, `address-review`, `ci-infra`,
   `ci-unknown`, `flip-*`) is `CODE_MERGE_PRECONDITION_UNMET`. This is what
   makes the flow in the issue literal — *the shepherd's merge decision* is the
   trigger — while keeping `decide()` the single source of merge eligibility.
   It also keeps the settle window, the fresh-findings filter and the
   required-check gates in force at the moment of the merge, not at the moment
   of the request.
6. **The gate.**
   ```
   run_gated(inp, pc.GITHUB_PR_MERGE, "merge", pr_ref,
             {"method": "merge", "delete_branch": True,
              "match_head_commit": pr.head_sha},
             side_effect=lambda: run_shepherd.merge_pr_unchecked(pr),
             metadata={"repo", "pr", "head_sha"},
             policy=configured_policy())
   ```
   The args are the same dict shape `run_shepherd.merge_pr` already digests, so
   the two paths describe the same class of action, and the head SHA is in the
   intent by construction.
7. **The side effect** is `run_shepherd.merge_pr_unchecked(pr)` (see §3): one
   `gh pr merge --merge --delete-branch --match-head-commit <SHA>` plus the
   re-read for the merge commit oid. It retries its own transient failures
   (secondary rate limit, 5xx) before raising, because every escape costs a
   human decision (`run_gated`'s contract). A non-zero `gh` exit that is *not*
   transient returns `(False, None)`, which the activity reports as
   `effect_error` → the wait's `effect_failed`.

Registered in `worker.py` beside `read_action_approval`.

### 3. The shepherd stops merging for gated services (`run_shepherd.py`)

- `SHEPHERD_MERGE_APPROVAL_SERVICES = _service_set_from_env(
  "SHEPHERD_MERGE_APPROVAL_SERVICES")` — same comma/whitespace parsing, same
  typo warning, unset = empty = today's behaviour.
- `_merge_gate_delegated(service) -> bool`.
- `merge_pr` is split: `merge_pr_unchecked(pr)` holds the `NEVER_MERGE_SERVICES`
  refusal, `refresh_github_token()`, the `gh` invocation and the snapshot
  re-read; `merge_pr(pr)` stays the checkpoint wrapper and behaves exactly as
  today. One extra guard at the top of `merge_pr`: for a gated service it
  prints `MERGE_GATED` and returns `(False, None)` **before** the checkpoint,
  so a pod can never create an approval request (defence in depth even if
  `MCTL_POLICY_APPROVALS=mctl-api` is set in the pod env).
- The tick's merge arm: `fix_only` for `decide()` becomes
  `mode == FIX_ONLY or _merge_gate_delegated(service)`, so a gated service
  yields `defer-merge` and `merge_pr` is never reached.
  `_merge_owner_for(service)` returns `devloop-workflow` for a gated,
  non-`NEVER_MERGE` service — descriptive metadata only, with the #344 warning
  repeated in its docstring. `.status.yaml`'s `status` is untouched, and
  `SHEPHERD_INPUT_STATUSES` (line 420) is unchanged, so the proposal keeps
  being reviewed and fixed exactly as before.
- Nothing about approvals is read or written by the shepherd. There is no
  ticket, no attempt counter, no denial counter.

### 4. `DevLoopWorkflow` becomes the first `run_gated_action` caller

In `_watch_pr`'s poll loop (`orchestrator/temporal/workflows/dev_loop.py`),
guarded by `workflow.patched("gated-merge")` so no existing history replays a
command it never recorded:

- **Identity.** On the first gate attempt, mint one execution context via the
  already-registered `mint_execution_context` activity
  (`activities/identity.py`) with `executor_type="devloop-workflow"` and this
  workflow's id, and keep `context_id`/`trace_id` in workflow state. Add
  `merge_gate_execution_id` / `merge_gate_trace_id` to `MergeWatchResume` so a
  `continue_as_new` hop keeps the same identity — the very property #484
  lacked. Additionally, extend `_merge_watch_hop_suggested` to refuse a hop
  while a merge-approval wait is in flight, mirroring its existing "never hop
  with an in-loop shepherd tick in flight" rule.
- **The call.** While the polled `PRState` is open, call
  `run_gated_action("merge_pull_request_gated", GatedActionInput(payload={repo,
  pr_number, head_sha, service, slug}, execution_id=..., actor=...,
  trace_id=...), poll_seconds=..., max_wait_seconds=remaining merge-watch
  budget)`. The wait is bounded by the receipt's own expiry minus
  `CONSUME_MARGIN_SECONDS` anyway; bounding by the remaining budget keeps the
  gate inside `MERGE_WATCH_DEADLINE`.
- **Outcomes.**
  | outcome | action |
  | --- | --- |
  | `ran` | log `MERGE_APPROVED` with `approval_ref`, approver, `decided_at`; the next poll sees `MERGED` and stages 6.2/6.3 proceed unchanged |
  | `blocked` (gate off, forbidden, precondition unmet, `approval_required`) | nothing; keep watching |
  | `mismatch` | the head moved; keep watching — the next poll asks about the new head, which is a new intent and a new human decision |
  | `denied`, `expired`, `timed_out` | log and keep watching; **never** call `next_attempt()` automatically, so nobody is re-asked the same question in a loop and a denial cannot be worn down |
  | `consumed`, `effect_failed` | never merge again on that receipt; re-read PR state and keep watching so a human sees it |
  | `already_waiting`, `undecided` | nothing this poll |
- Cancellation (`abandon`/`terminate` during the merge watch, #420) propagates
  to the child wait; an unconsumed receipt simply expires.

### 5. Docs

- ADR-014 §7: mark the merge gate as the first adopter of `run_gated_action`;
  update open decision 3.
- `docs/adr/017-shepherd-merge-approval.md`: the decision record for this
  design and an explicit "why the #484 `ApprovalTicket` is not repairable".
- `docs/runbooks/shepherd-merge-approval.md`: adapted from #484's runbook —
  how to enable the two env vars, how to approve/deny through mctl-api's
  action-approval routes, how to read `POLICY_DECISION` / `MERGE_GATED` /
  `MERGE_APPROVED`, and the documented consequences (a flag flip mid-wait is a
  mismatch; a gated service with no live DevLoop does not merge).
- `README.md` shepherd section: the new env var next to
  `SHEPHERD_FIX_ONLY_SERVICES`, and `defer-merge`'s new `merge_owner`.

## Alternatives

1. **Repair #484: keep the `ApprovalTicket` in `.status.yaml` and resume it on
   a later tick.** Dropped, and explicitly forbidden by the issue. The intent
   hash contains `execution_id`; a new pod means a new identity, so the
   receipt can only ever come back `mismatch`. Making it work would require
   either dropping `execution_id` from the intent (weakening the binding
   mctl-api enforces) or minting a synthetic long-lived identity shared by
   unrelated pods (an identity that names no execution). It also puts approval
   state in a gitops file that the reconciler, the implementer and the steward
   all write — the #344 misreading risk in its most dangerous form.

2. **A new `ShepherdMergeWorkflow` started by the shepherd pod, one per
   (repo, PR, head SHA).** Gives a durable execution for cron-only PRs too.
   Dropped for this slice: the pod cannot start a Temporal workflow today (it
   has no Temporal client; `orchestrator/temporal/start.py` runs control-plane
   side), so it needs a new mctl-api route — a cross-repo dependency the issue
   asks us to avoid — plus a second workflow type whose only job is to call
   `run_gated_action`. Recorded as the natural follow-up for the cron case.

3. **Trigger the gate on GitHub's own `mergeable_state == CLEAN` and skip
   `decide()`.** Cheapest, no shepherd coupling at all. Dropped because codex
   findings are not GitHub checks: a P1 inline comment on the current head
   leaves a PR "clean" to GitHub, so this would ask a human to approve a merge
   the shepherd would have refused, discarding the fresh-findings filter
   (#359/#336) and the settle window.

4. **Pass the shepherd's verdict to DevLoop through a new `.status.yaml`
   field.** Dropped: the tick's own decision is cheap to recompute in the
   activity from the same pure `decide()`, and any new gitops field about
   merge readiness is exactly what #344 warns gets read as an authorization.

## Platform impact

**Migrations.** None. No schema, no `.status.yaml` shape change, no new store.
`MergeWatchResume` gains two optional string fields, which older recorded
payloads deserialize as empty (the same additive rule `WorkflowResult` already
relies on).

**Backward compatibility.** Zero behaviour change until gitops sets both
`MCTL_POLICY_MERGE_APPROVAL=require` (worker and shepherd CWFT) and
`SHEPHERD_MERGE_APPROVAL_SERVICES=<service>`; the gated activity's first check
short-circuits, so an unset flag costs one cheap activity per 15-minute poll.
`MCTL_POLICY_APPROVALS=mctl-api` must also be set **on the worker** for a
request to be created at all; without it the gate is `approval_required` →
`blocked` → no merge, which is fail-closed. `workflow.patched("gated-merge")`
means in-flight loops never enter the gate; only executions started after the
deploy do (the `patched()`-memoization rule ADR-008 records).

**Resource impact.** Per merge-watch poll, when the gate is on: 1 Temporal
activity, ~4 `gh` API reads (PR snapshot, reviews, review comments, checks) —
the same reads the shepherd tick already performs, so roughly a doubling of
that PR's read traffic on the gated service. The wait itself holds no pod and
no activity; its cost is one durable timer plus one read-only GET every 15
minutes.

**Risks and mitigations.**
- *A gated service with no live DevLoop stops merging.* Mitigation: per-service
  opt-in, a greppable `MERGE_GATED` line per held PR, and the runbook naming
  the manual merge path. Recorded as open question 1.
- *A burned receipt after a partial merge (`effect_failed`).* Mitigation: the
  side effect re-reads the PR and is idempotent by `--match-head-commit`; the
  receipt is never retried; the outcome is logged and surfaces to a human.
- *Double merge.* Structurally impossible: one receipt, consumed atomically by
  mctl-api before the effect; retries and replays get `approval_consumed`; a
  second waiter gets `already_waiting`.
- *Approval fatigue / a denial worn down by retries.* Mitigation: no automatic
  `next_attempt()`; one request per (intent, head SHA) by the deterministic
  idempotency key.
- *Worker GitHub token drift.* `merge_pr_unchecked` keeps
  `refresh_github_token()` exactly where `merge_pr` has it today (the comment
  at run_shepherd.py:2608 explains why the merge needs its own refresh).
- *Policy-version churn.* A flag flip mid-wait invalidates a pending receipt as
  `mismatch`; documented, fail-closed, and recoverable by re-approving.
