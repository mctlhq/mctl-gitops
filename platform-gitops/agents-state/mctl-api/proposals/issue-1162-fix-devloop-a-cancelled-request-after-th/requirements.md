# Deliver the DevLoop approve and abandon signals reliably after the decision is recorded

## Context

On the DevLoop decide page the approval decision is committed first
(`decideDevLoopApproval` writes the grant to `approved`), and the Temporal
`approve` signal is sent second, on the HTTP request context
(`ApproveDevLoopWorkflow` in `internal/api/handlers_dev_loop.go`). If that
context is cancelled between the two steps (client disconnect, aborted
redirect, pod shutdown), the grant stays `approved` and is never `consumed`. The
proposal stays `proposed`, and the workflow stays parked on the approve signal
with nothing logged. Reopening the link leads nowhere ("already approved,
nothing left to decide" or "already used"). This happened on 2026-11-22 to
`dev-loop-mctlhq-.github-41` (grant `aar_10a43ccaf863441c85974a33848a20da`). The
cancel came 35 ms after the decision, and an operator fixed it by hand with
`mctl_approve_dev_loop`.

The abandon signal (`AbandonDevLoopWorkflow`) uses the same request-bound
context. This is the same class of bug as the release-window settle fix
(#1156), which detached only that path. This proposal detaches both DevLoop
signals from the request. It also adds a background redelivery path for
approved-but-unconsumed DevLoop grants, a page state that offers a retry in
place of a dead end, and a metric plus logs for the partial state.

## User stories

- AS a platform admin approving a DevLoop on the decide page I WANT my recorded approval to reach the workflow even if my browser drops the request SO THAT the DevLoop proceeds without operator intervention.
- AS a platform admin reopening a decide link for a grant that is approved but not consumed I WANT to see that state and retry the delivery SO THAT I am not stuck at "Could not decide".
- AS an operator I WANT a metric and an alert for approved DevLoop grants that stay unconsumed SO THAT a stuck delivery is visible before someone asks why a DevLoop is idle.
- AS an operator abandoning a DevLoop I WANT the abandon signal to survive my client disconnecting SO THAT the loop really ends.

## Acceptance criteria (EARS)

- WHEN `ApproveDevLoopWorkflow` sends the approve signal THE SYSTEM SHALL send it on a context derived with `context.WithoutCancel` from the request context and bounded by its own deadline (`devLoopSignalTimeout`, default 15s), so cancelling the request does not cancel the signal.
- WHEN `AbandonDevLoopWorkflow` sends the abandon signal THE SYSTEM SHALL use the same detached, deadline-bounded context.
- IF the request context is cancelled after `decideDevLoopApproval` recorded the decision and before the signal returned THEN THE SYSTEM SHALL still deliver the signal with the grant's `approval_ref`.
- WHILE a `mctl-agents-approve` grant is `approved`, not consumed, not expired, and decided more than `devLoopRedeliverMinAge` (default 2 minutes) ago THE SYSTEM SHALL treat it as an unfinished delivery.
- WHEN the redelivery reconciler finds such a grant whose execution's Temporal run is `Running` THE SYSTEM SHALL re-send the approve signal with payload `{"approval_ref": <grant id>}` to that workflow (pinned to the run when the engine_ref pins one).
- IF the run is closed, not found, or cannot be described THEN THE SYSTEM SHALL NOT send a signal, and SHALL log the grant id, the workflow id and the reason.
- WHEN the reconciler re-sent a signal for a grant less than `devLoopRedeliverBackoff` (default 10 minutes) ago in this process THE SYSTEM SHALL NOT send it again in that pass.
- WHEN a grant is `consumed` (or otherwise no longer `approved`) THE SYSTEM SHALL NOT select it for redelivery, so a pass after a successful delivery sends nothing.
- THE SYSTEM SHALL run the reconciler from durable store state only (no in-memory record of decisions), so any replica, including one started after the deciding pod is gone, recovers the grant.
- WHEN the decide-page callback reads the bound grant in state `approved` THE SYSTEM SHALL render a page stating that the approval is recorded but its delivery to the DevLoop is not confirmed, and SHALL offer a "Retry delivery" action in place of "Could not decide".
- WHEN the signed-in admin confirms "Retry delivery" THE SYSTEM SHALL re-send the approve signal through `ApproveDevLoopWorkflow` with the same binding. No new decision is recorded, because the approved branch of `decideDevLoopApproval` returns the existing grant id.
- WHEN the decide-page callback reads the grant in state `consumed`, `in_flight` or `executed` THE SYSTEM SHALL say the approval was already delivered, not that the decision is unknown or used.
- THE SYSTEM SHALL expose a gauge `mctl_devloop_approval_undelivered` (approved, unconsumed DevLoop grants older than `devLoopRedeliverMinAge`, set on each reconciler pass) and a counter `mctl_devloop_approval_redeliveries_total{outcome}` (`signalled`, `run_closed`, `describe_failed`, `signal_failed`).
- WHEN a grant is found undelivered THE SYSTEM SHALL log at WARN with `workflow_id`, `approval_ref`, `execution_id` and the grant's age.
- WHEN the reconciler re-sends a signal THE SYSTEM SHALL write an audit entry with operation `dev-loop-approve-redeliver`, the workflow id and the approval ref, and `UserID` set to the service principal.

## Out of scope

- Changing the worker (mctl-agents) signal handling. The design relies on the existing behaviour that the worker refuses a grant it has already exercised.
- Rolling back a recorded decision when the signal fails.
- Redelivering abandon signals in the background. Abandon records no durable decision in mctl-api that a reconciler could find. Detaching the signal and the existing 502 (which the caller can retry) cover it.
- The release-window path (already fixed in #1156) and other approval kinds (deploy, glovo).
- A Prometheus alert rule in this repo. No `PrometheusRule` exists under `helm/`. The alert is a follow-up in the monitoring config (see Open questions).

## Open questions

- Grant freshness: `DecideActionApproval` sets `fresh_until` when `FreshFor > 0`. If the DevLoop approval freshness bound is shorter than the reconciler's min age plus its interval, a redelivered grant could be refused at consume. The design assumes the bound is at least tens of minutes. The implementer should check `h.opts` for the DevLoop `FreshFor` value and keep `devLoopRedeliverMinAge` well below it.
- Where the "undelivered approval" alert rule lives (mctl-gitops monitoring config vs. a chart template). This proposal only exposes the metric and suggests the expression `mctl_devloop_approval_undelivered > 0 for 10m`.
- Multiple replicas: the in-process backoff is per pod (`helm/values.yaml` has `replicaCount: 1`, and the deployed replica count was not observable). With N replicas a grant may be re-sent up to N times per backoff window. This is harmless because the signal is idempotent per grant id, but it is not literally once across pods.
