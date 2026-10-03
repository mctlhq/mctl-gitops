# Design: issue-349-a-proposal-committed-straight-to-accepte

## Current state

**The gate.** `human_approval_satisfied(data)` in
`orchestrator/proposal_state.py:60-112` is the single predicate. It returns
`True` when there is no `control` block at all (the incident-responder path,
`orchestrator/run_incident_responder.py:20-23`, writes `accepted` with no
control block and would otherwise be stranded), returns `True` when
`requires_human_approval` spells one of `_FALSEY`, and otherwise requires
`approval.approved_by` to be a string that is not in `_ANONYMOUS_APPROVERS`
(`{"", "unknown", "none", "null"}`). A bare `status: accepted` clears nothing.
That behaviour is correct and this proposal does not touch it.

**Where the gate is read.** `find_accepted_proposals()`
(`orchestrator/run_implementer.py:258-327`) computes `approval_ok` while it
already has the parsed status file in hand and carries it on `ProposalRef`
(fail-closed default `False`, `run_implementer.py:164-186`). `implement_one()`
consumes it at `run_implementer.py:1166-1176` and returns:

```python
return ImplementResult(
    ref=ref, pr_url=None,
    skipped_reason=("requires_human_approval is set but no verified approval is "
                    "recorded; approve through the dev-loop endpoint, ..."),
    counts_toward_limit=False,
)
```

**Why that is invisible.** `ImplementResult` has exactly three outcome channels:
`error`, `skipped_reason`, `pr_url` (`run_implementer.py:188-194`). The refusal
uses `skipped_reason`, so:

- `_implement_refs()` (`run_implementer.py:1400-1433`) prints
  `Finished: skipped` — the same marker a dry-run or a closed-PR adoption
  prints.
- `_batch_outcome()` (`run_implementer.py:1436-1448`) increments `skipped`.
- `main()` (`run_implementer.py:1580-1588`) exits non-zero only on
  `outcome.failed`, so the process exits `0`.
- Nothing is written to `.status.yaml`, so the mctl-gitops `commit-and-push`
  step reports `No .status.yaml updates handed off — nothing to commit`.

Every observable surface of a permanently blocked run is identical to a healthy
no-work run. `counts_toward_limit=False` additionally means the refusal never
consumes the `--max-proposals 1` budget (`run_implementer.py:1451-1462`), so the
run repeats forever at no cost and with no trace.

**Why the message is wrong.** It sends the operator to the dev-loop approve
endpoint, which signals a running `DevLoopWorkflow`. That workflow only exists
when the issue came through `orchestrator/temporal/start.py`, keyed by
`workflow_id_for()` (`orchestrator/temporal/issue_ref.py:30-37`) as
`dev-loop-mctlhq-<repo>-<issue>`. A proposal authored outside that path — the
reproduction in the issue was written by `claude-code-e2e-verification` — has
none, and the message names no other route.

**Why nothing else catches it.** `run_shepherd.py` reconciles `accepted`
proposals but returns `decision="wait"` when there is no PR
(`run_shepherd.py:2105-2108`). The orphan sweep
(`orchestrator/temporal/activities/orphans.py:25,57-76`) only reports proposals
that *have* an open PR. A blocked proposal has neither, so it falls through
every sweep.

**Where the flip lives.** `mctl-agents-approve` is an Argo CWFT in mctl-gitops
(`cwft-mctl-agents-approve.yaml`, referenced from
`orchestrator/proposal_state.py:48` and submitted by
`orchestrator/temporal/workflows/dev_loop.py:620-640`). This repository contains
no code that performs the flip, so "make approve record an approver" is not a
change that can be made here.

## Proposed solution

Three changes, all inside mctl-agents, all in the direction the issue calls the
more valuable half: make the refusal loud, durable and correctly explained, and
stop this repo from ever minting the combination again.

### 1. A named outcome: `blocked`

`orchestrator/proposal_state.py` gains one exported predicate so the meaning
lives beside the gate rather than inline in the implementer:

```python
BLOCKED_APPROVAL_MISSING = "approval-missing"

def unrunnable_reason(data: dict[str, Any]) -> str | None:
    """Stable code when a proposal can never run as written, else None."""
    if data.get("status") != "accepted":
        return None
    return None if human_approval_satisfied(data) else BLOCKED_APPROVAL_MISSING
```

`ImplementResult` gains `blocked: str | None = None` (the stable code;
`skipped_reason` keeps the human text so no existing consumer breaks).
`BatchOutcome` gains a trailing `blocked: int = 0` — trailing with a default so
`tests/test_run_implementer_summary.py`'s equality assertions against
`BatchOutcome(succeeded=1, failed=1, skipped=1)` keep passing unchanged.
`_batch_outcome()` classifies in the order `error -> blocked -> skipped_reason ->
pr_url`, so a blocked proposal never inflates the skip count.
`_implement_refs()` prints `Finished: blocked`. `main()` prints a dedicated
`=== Blocked ===` section and the four-way `Totals:` line.

Exit-code rule in `main()`, in this order:

```
outcome.failed                            -> sys.exit(1)               # unchanged
outcome.blocked and not outcome.succeeded -> sys.exit(EXIT_BLOCKED_ONLY)  # 45
otherwise                                 -> return (0)
```

`45` joins the existing sentinel table (`EXIT_NO_FOLLOWUP_COMMITS = 42`,
`EXIT_BRANCH_MISSING_ON_ORIGIN = 43`, `EXIT_OPERATION_TIMEOUT = 44`,
`run_implementer.py:128-161`). The `succeeded > 0` carve-out is deliberate: a
run that already opened a PR has durable `.status.yaml` writes pending, and a
non-zero exit should not risk the mctl-gitops `commit-and-push` step that
carries them. (As of 2026-09-12 that step runs regardless — see the risk note
below — so this is defence in depth rather than the load-bearing reason. The
carve-out stands on its own: a run that did real work should not report red.)
In that case the blocked proposal is still reported in its own section and
still gets the durable marker below. `--dry-run` never changes the exit code.

### 2. A durable marker, written once

When the gate fires outside `--dry-run`, the implementer annotates the proposal
in place. `status` stays `accepted` — the proposal genuinely is accepted and
un-approved, and moving it to `needs-triage` would both misdescribe it (nothing
was attempted) and destroy the state a future in-place approval fix would act
on:

```yaml
status: accepted
control:
  requires_human_approval: true
blocked:
  code: approval-missing
  since: '2026-09-12T09:14:00Z'
  message: >-
    control.requires_human_approval is set but no approval.approved_by is
    recorded, and the proposal is already accepted ...
  remedy: >-
    Signal DevLoopWorkflow dev-loop-mctlhq-mctl-design-21 ... / re-publish in
    proposed status ...
```

`_mark_blocked()` reads the current file first and returns without writing when
the existing `blocked.code`, `message` and `remedy` all match, preserving the
original `since`. Because the block carries no per-tick timestamp, a
permanently blocked proposal produces exactly one gitops commit, not one per
30-minute tick — this is the property that makes writing to gitops from a
polling loop acceptable at all.

The marker is cleared by passing `blocked=None` at the four call sites that
already clear `failure`: the `in-progress` transition
(`run_implementer.py:1260`) and the `open` / `merged` / `closed` adoptions
(`run_implementer.py:1192-1228`). `update_status_file()`'s existing
`None`-removes-a-field semantics (`proposal_state.py:115-141`) make this a
one-keyword change per site. `_mark_needs_triage()` deliberately does not clear
it: a failed attempt is a different fact.

### 3. An honest message, derived from the proposal's own state

`_approval_blocked_message(ref)` builds the text from the `source` block the
implementer already reads for `_issue_closing_line()`
(`run_implementer.py:929-952`), reusing `workflow_id_for()` from
`orchestrator/temporal/issue_ref.py` — which is deliberately temporalio-free so
the agent container can import it (see its module docstring).

- Always: `mctl-agents-approve` only performs the `proposed -> accepted` flip
  and is a no-op here, so no supported path records an approver in place
  (mctl-agents#349); the verified recovery is to re-publish the proposal in
  `proposed` status, where the flip really happens.
- With a `github_issue` source: additionally name
  `dev-loop-mctlhq-<repo>-<N>` and the
  `POST /api/v1/agents/dev-loop/<id>/approve` endpoint, qualified with "if that
  execution is still running".
- Without one: state plainly that no DevLoopWorkflow exists for this proposal,
  and do not mention the endpoint.
- Never: suggest hand-editing `approval.approved_by`. The issue is explicit that
  this forges the exact record the gate exists to require.

### 4. Refuse to mint the combination (the issue's direction 3)

`update_status_file()` gains a guard that raises a new
`UnrunnableProposalError` when the write would *introduce* the unrunnable state:
the merged payload is `accepted` with `unrunnable_reason() is not None`, and the
payload previously on disk was not already in that state. Comparing against the
previous on-disk payload rather than refusing unconditionally is what keeps
`_mark_blocked()` legal — the guard must never prevent the diagnosis of state it
did not create, and an explicit bypass keyword would be one more knob to get
wrong.

This is defence in depth for future in-repo writers. It cannot stop an external
tool committing YAML straight into mctl-gitops, which is how the reproduction
proposal was created; that hole closes only with a validation hook in
mctl-gitops, tracked as a follow-up.

## Alternatives

1. **Let the implementer record the approval itself when it sees `accepted`.**
   Dropped outright. It forges the exact record the gate exists to require, and
   the issue names hand-writing `approval.approved_by` as explicitly not a
   workaround. It would silently re-open gitops#986 from inside the component
   that was built to close it.

2. **Flip blocked proposals to `needs-triage`.** Rejected. `needs-triage` is
   written by `_mark_needs_triage()` and means "an attempt ran and could not be
   completed"; it is paired with a `failure` block that the shepherd reads
   (`run_shepherd.py:291-320`, `2116-2124`). A blocked proposal was never
   attempted. Worse, it would erase `status: accepted`, which is the state a
   future mctl-gitops fix ("record an approver on an already-accepted proposal")
   needs in order to act at all — the code change here would make the
   cross-repo fix harder.

3. **Fix only in mctl-gitops: let `mctl-agents-approve` write
   `approval.approved_by` on an already-accepted proposal.** This is the right
   change and should still happen, but it cannot be the whole fix and cannot be
   made from this repository. It repairs one proposal shape and leaves the
   general defect — a green implement run that did nothing is indistinguishable
   from one that did work — exactly where it is. The issue itself argues (2) is
   the more valuable half "regardless of (1)".

4. **Emit a Telegram notification from the implementer process.** Rejected. The
   notify step is a CWFT step in mctl-gitops (`notify-telegram`), the
   orchestrator has no notification client and no bot credentials, and adding
   one duplicates a channel that already exists one layer up. A non-zero exit
   reaches that same channel through the workflow's own failure path.

## Platform impact

**Migrations.** None. `blocked` is a new optional key in a durable projection
whose every writer already preserves unknown fields
(`update_status_file()` merge semantics, `proposal_state.py:115-141`). Existing
`.status.yaml` files are unaffected until an implement run touches them.

**Backward compatibility.**
- `BatchOutcome` gains a trailing defaulted field, so positional and keyword
  construction in existing tests keeps working.
- `ImplementResult.skipped_reason` is still set on a blocked result, so any
  consumer that only reads the old channel still sees a human-readable reason.
- `--review-feedback` mode selects `{implemented, review-fixing}`
  (`run_implementer.py:1518-1523`) and never evaluates the gate: unchanged.
- The `mctl-agents-implement` CWFT contract is unchanged apart from the exit
  code; no new parameters.

**Resource impact.** Negligible: one extra `.status.yaml` read per blocked
proposal per run, and at most one extra gitops commit per blocked proposal for
its entire lifetime.

**Risks and mitigations.**

- *A non-zero implement step may cause mctl-gitops to skip `commit-and-push`,
  discarding the blocked marker in a blocked-only run.* **Not a risk — resolved
  2026-09-12 by reading the CWFT.** `cwft-mctl-agents-implement.yaml` sets
  `continueOn: {failed: true, error: true}` on both `implement` and
  `implement-fallback`, and `commit` is the next unconditional step — put there
  for exactly this reason ("those updates would never persist back to
  mctl-gitops main"). The marker survives a blocked-only run, so no follow-up is
  needed and none should be filed.

  The original mitigation is recorded here because it is what makes the design
  robust if that ever changes: the marker write happens before the exit-code
  decision, the red workflow is the primary signal and does not depend on the
  commit, the write is idempotent so any later run that does commit will carry
  it, and the `succeeded > 0` carve-out guarantees a run with real work still
  exits `0`.
- *A red workflow where operators previously saw green could be read as a
  regression.* That is the intent, and it is bounded: the code only fires when a
  proposal is provably unrunnable. The dedicated exit code `45` and the
  `=== Blocked ===` section let an operator tell it from a genuine failure at a
  glance.
- *DevLoopWorkflow sees the implement CWFT fail for a blocked proposal.* Correct
  behaviour — the loop did not implement — and it surfaces on the workflow
  rather than being swallowed. The loop's own approve step already stops on a
  failed flip (`dev_loop.py:641-648`), so the shape is familiar.
- *The new `update_status_file()` guard could break an unforeseen writer.* Only
  writers that produce `accepted` are affected; today that is the
  incident-responder (no control block, so still permitted) and the mctl-gitops
  approve CWFT (not this code path). The guard is scoped to writes that
  *introduce* the state, so annotating already-broken proposals stays legal.
- *Marker churn in gitops.* Prevented by the equality check in `_mark_blocked()`
  and by omitting any per-observation timestamp from the block. This is
  explicitly a test, not just a convention (T4).
