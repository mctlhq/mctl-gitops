# Design: issue-1162-fix-devloop-a-cancelled-request-after-th

## Current state

**Approve path.** `internal/api/handlers_dev_loop.go`:
- `ApproveDevLoopWorkflow` calls `h.decideDevLoopApproval(...)`. For a `pending` `mctl-agents-approve` grant on the decide page, that function commits the decision through `h.opts.WorkItems.DecideActionApproval` and audits `action_approval.decision`. It then returns the grant id as `ref`.
- The handler then calls `h.opts.TemporalClient.SignalApprove(r.Context(), workflowID, payload)` with `payload["approval_ref"] = ref`, at about line 637. On error it audits `dev-loop-approve` `failed` with `"signal failed: ..."` and answers 502 (or 503 for `temporalclient.ErrUnavailable`, 404 for NotFound). Nothing undoes the decision and nothing retries.
- `decideDevLoopApproval` already handles a re-send. In its `case workitems.ApprovalApproved:` branch it returns the existing grant id without deciding anything (checking the binding against `newest.DecidedContextDigest`), "so a retry after a lost signal re-sends it". This is the path the manual recovery with `mctl_approve_dev_loop` used. It needs no decide-page privilege, because `mayDecideDevLoop` is consulted only for pending or legacy grants.

**Abandon path.** `AbandonDevLoopWorkflow` describes the execution on `context.WithTimeout(r.Context(), devLoopDescribeTimeout)`. It then calls `SignalAbandon(r.Context(), workflowID, exec.RunID, payload)`, with a comment stating the signal is "bounded only by the request context, as SignalApprove is ... Change both together".

**Temporal client.** `internal/temporalclient/client.go`: `SignalApprove` sends `ApproveSignalName` with an empty run id (latest run). `SignalAbandon` pins the run. No query exposes "parked on approve". The `DevLoopClient` interface (`internal/api/interfaces.go`) offers `DescribeDevLoopRun(ctx, wf, runID)`.

**Decide page.** `internal/api/handlers_devloop_decide.go`:
- `handleDevLoopDecideCallback` reads the grant via `callAs(... h.GetDevLoopApproval)`. It checks the binding, then refuses any state other than `pending` with `d.failed(..., "This approval is already <state>; there is nothing left to decide.")`. The page title is "Could not decide".
- `handleDevLoopDecideConfirm` marks the challenge `decideUsed` and drops it before acting. Re-posting it therefore answers "unknown, expired, already used ...". That is the dead end in the incident.
- Approve runs `h.ApproveDevLoopWorkflow` in-process through `callAs(r.WithContext(withDecidePage(r.Context())), ...)`, so the request context of the browser POST is the one that reaches `SignalApprove`.

**Precedent for detaching.** `internal/api/handlers_release_window_execute.go` `settleContext` uses `context.WithTimeout(context.WithoutCancel(parent), d)` (#1156). The same pattern appears in `handlers_deploy_apply.go:671` and `handlers_submit_execution.go:168`.

**Precedent for a reconciler.** `internal/api/execution_orphan_reconciler.go` defines `ReconcileOrphanedExecutions(ctx, store, tc, now)`. It is started from `cmd/api/main.go` (about line 1245) on a `time.NewTicker(mctlapi.OrphanReconcileInterval)` under `rootCtx`, with a per-pass `context.WithTimeout(rootCtx, time.Minute)`. It pages candidates with a keyset cursor, describes the run, fails closed on an unreadable run, and uses `parseTemporalRef` to split `engine_ref` (`<wf>`, `<wf>#run_<id>`, `<wf>#xr_...`).

**Store.** `internal/workitems/action_approvals.go`: `ActionApprovalRequest` has `ExecutionID`, `State`, `DecidedAt`, `ConsumedAt`, `ExpiresAt` and `DecidedContextDigest`. `ActionApprovals(ctx, ActionApprovalFilter{State, ExecutionID, ActionKind, RequestedBy, Limit})` lists newest first on the effective state, where `expired` overrides an approved row past `expires_at`. There is no decided-before filter and no cursor. `Store.ExecutionByID` loads an execution (`internal/workitems/store.go`). The grant kind constant is `devLoopApprovalKind = "mctl-agents-approve"` (`handlers_action_approvals.go`).

**Metrics.** The repo uses `prometheus.NewCounterVec` package vars (for example `approvalBindingAbsentTotal` in `approval_binding.go`). `helm/` has no `PrometheusRule`.

**Deployed state checked:**
- `mctl_get_service_status(team=admins, service=mctl-api)`: "ArgoCD application not found: admins-mctl-api". mctl-api is not a tenant service under that name, so its deployed replica count and env were not observable through this tool.
- `$MCTL_GITOPS_ROOT/services/*/`: has no `mctl-api` directory (searched `services/admins/`). The deployed values were not observed. The only replica evidence is the chart default `helm/values.yaml` `replicaCount: 1`, plus the issue naming a single pod `mctl-api-6c5df5d5bf-xkwnk` (4.173.0). The replica count is recorded under Open questions in requirements.md. The design does not depend on it.

## Proposed solution

### 1. Detach both signals (handlers_dev_loop.go)

Add a helper next to the DevLoop timeouts:

```go
const devLoopSignalTimeout = 15 * time.Second

// devLoopSignalContext detaches a Temporal signal from the request: once a
// decision is recorded, a client disconnect must not cancel its delivery
// (mctl-api#1162, same class as #1156's settleContext).
func devLoopSignalContext(parent context.Context) (context.Context, context.CancelFunc) {
    return context.WithTimeout(context.WithoutCancel(parent), devLoopSignalTimeout)
}
```

Use it for `SignalApprove` in `ApproveDevLoopWorkflow` and for `SignalAbandon` in `AbandonDevLoopWorkflow`, and replace the "bounded only by the request context" comment. `WithoutCancel` keeps context values (trace, user), so audit and tracing are unchanged. Error mapping (404/502/503) is unchanged. The HTTP response may then fail to write if the client is gone, which is fine. The audit records the true outcome.

### 2. Redelivery reconciler (new `internal/api/devloop_approval_redeliver.go`)

```go
const (
    DevLoopRedeliverInterval = 2 * time.Minute
    devLoopRedeliverMinAge   = 2 * time.Minute  // > signal timeout + worker consume latency (~30s observed)
    devLoopRedeliverBackoff  = 10 * time.Minute
    devLoopRedeliverBatch    = 20
)

type DevLoopRedeliverer struct { store redeliverStore; tc DevLoopClient; audit ...; mu sync.Mutex; lastSent map[string]time.Time; now func() time.Time }
func (r *DevLoopRedeliverer) Pass(ctx context.Context) (signalled int)
```

For each pass:
1. List candidates with a new store method `UndeliveredActionApprovals(ctx, kind string, decidedBefore time.Time, limit int, after *ActionApprovalRequest)`. It selects rows with `action_kind=$1 AND state='approved' AND consumed_at IS NULL AND decided_at < $2 AND expires_at > now()`, keyset-ordered by `(decided_at, id)`. Because it reads the stored state, an approved-past-expiry grant is excluded, matching the effective-state rule. Set the gauge to the total count found.
2. For each grant: skip if `lastSent[id]` is within the backoff. Otherwise load `ExecutionByID(grant.ExecutionID)`, then `parseTemporalRef(exec.EngineRef)`, then `DescribeDevLoopRun(ctx, wf, runID)`.
   - If the describe fails or the status is Unknown: count `describe_failed` and skip. This fails closed, as `orphanEngineStatus` does.
   - If the run is NotFound or closed: count `run_closed`, log WARN, and skip. Nothing is waiting for the signal, and the orphan reconciler or an operator owns the execution.
   - If the run is `Running`: call `SignalApprove(sigCtx, wf, {"approval_ref": grant.ID})`, with `sigCtx` from `devLoopSignalContext(ctx)`. Record `lastSent`, count `signalled` (or `signal_failed`), and audit `dev-loop-approve-redeliver` as the service principal. `SignalApprove` targets the latest run of the workflow id. A pinned engine_ref whose pinned run is no longer the latest is skipped, so a different run never gets the signal.
3. Prune `lastSent` entries older than the backoff.

**Why this is safe to repeat.** The payload carries only the grant id. The worker exercises the grant through `POST /api/v1/action-approvals/{id}/consume` (`ConsumeActionApproval`, an atomic approved-to-consumed compare-and-set) and refuses a grant it already exercised. A second signal is therefore at worst a no-op. Once the grant is consumed it drops out of step 1, so a later pass sends nothing.

**Why it survives a restart.** The reconciler holds no state about which pod decided. It reads the durable grant row and the Temporal run, so any replica started at any time recovers the grant.

Wiring in `cmd/api/main.go`: start it alongside the orphan sweeper when `workItemsStore != nil && devLoopClient != nil`. Unlike the orphan sweeper, it is not gated on `queueWhileActive`. Use the same ticker pattern under `rootCtx`, with a per-pass `context.WithTimeout(rootCtx, time.Minute)`. An env switch `DEVLOOP_APPROVAL_REDELIVER_ENABLED` (default `true`) gives a kill switch without a code change.

### 3. Decide page: "approved, delivery not confirmed" (handlers_devloop_decide.go)

In `handleDevLoopDecideCallback`, the binding check still runs first. After it, replace the single `state != pending` refusal with:
- `pending`: unchanged.
- `approved`: advance the challenge to `decideSignedIn` with a CSRF token, as for pending, and render the title "Approved, delivery not confirmed". The page text says: "This approval was recorded at <decided_at> but the DevLoop has not picked it up yet. It is retried automatically; you can retry the delivery now." It offers a single button, `decision=redeliver`.
- `consumed`, `in_flight`, `executed`: render the title "Already approved" and the text "The DevLoop received this approval." This is an informational page, not a failure.
- `denied`, `expired`: keep the current refusal text.

In `handleDevLoopDecideConfirm`, accept `decision == "redeliver"`. It calls `ApproveDevLoopWorkflow` with the same binding (through `withDecidePage`, unchanged), which reaches the `ApprovalApproved` branch and only re-sends. It renders "Delivery retried" on 200. A pending grant posted with `redeliver` is rejected: the callback recorded the state the page offered, so the challenge stores `offered string` and the confirm checks that the posted decision matches it.

`GetDevLoopApproval` returns the context digest the binding compares against. For an approved grant the page must compare `bind.ContextDigest` with `decided_context_digest`, mirroring `bindingMatches(bind, &newest, newest.DecidedContextDigest)`. The callback's `got` struct gains `approval.decided_context_digest` and `approval.decided_at` for this purpose.

### 4. Visibility

Add `devLoopApprovalUndelivered` (`prometheus.NewGauge`, `mctl_devloop_approval_undelivered`) and `devLoopApprovalRedeliveries` (`NewCounterVec`, label `outcome`), registered the way the existing package-level metrics are. Log each undelivered grant at WARN with `workflow_id`, `approval_ref`, `execution_id` and `age`. The suggested alert is `mctl_devloop_approval_undelivered > 0 for 10m`; where it lives is an Open question.

## Alternatives

1. **Detach only (no reconciler).** This fixes the client-disconnect case but not a pod shutdown during the signal or a Temporal blip that outlasts the 15s deadline. It leaves the same unfinished state, and the issue explicitly asks for guaranteed redelivery. Rejected as incomplete.
2. **Transactional outbox: write a "signal pending" row in the decision transaction and have a dispatcher deliver it.** This is the strongest guarantee, and `internal/events/relay.go` shows the pattern exists. But it needs a migration and a change to `DecideActionApproval`'s transaction, and it duplicates state the grant row already carries (`approved` and not `consumed` *is* the outbox entry). Rejected as more machinery for the same guarantee.
3. **Have the worker poll mctl-api for its grant while parked.** This puts the fix in mctl-agents, which belongs to another repo and release cycle. The parked `wait_condition` would need a timer loop and an API read per tick. It also leaves the mctl-api page dead end unaddressed. Kept as a possible defence-in-depth follow-up and not part of this proposal.
4. **Roll the decision back when the signal fails.** This reverses a human decision because of a transport error, and it is racy, since the signal may in fact have been delivered before the error surfaced. Rejected.

## Platform impact

- **Migrations:** none required. The candidate query uses existing columns. If `action_approval_requests` has no index covering `(action_kind, state, decided_at)`, add a partial index `WHERE state='approved'` in a migration. The implementer checks the existing indexes first. Volume is small (DevLoop approvals number in the tens per day).
- **Backward compatibility:** API responses and status codes are unchanged. The decide page gains states and one form value (`redeliver`); old links keep working. The worker contract is unchanged (same signal name and payload).
- **Resource impact:** one indexed query every 2 minutes, plus one describe per candidate (normally zero candidates).
- **Risks and mitigations:**
  - Duplicate signals across replicas or passes: the worker is idempotent per grant id, and consume is a compare-and-set. There is a per-pod backoff.
  - Signalling a run that is not parked on approve (for example one that is re-investigating after a superseded grant): a superseded grant is no longer the newest, but it may still be `approved`. The worker refuses a grant that is not its current one. The reconciler also skips a grant whose execution is no longer open (closed executions are not candidates for delivery).
  - A detached signal outliving pod shutdown: it is bounded by `devLoopSignalTimeout` (15s), which is within the default termination grace period.
  - Freshness bound shorter than the redelivery delay: see the Open question. The min age is configurable.
- **Rollback switch:** `DEVLOOP_APPROVAL_REDELIVER_ENABLED=false` disables the reconciler without a redeploy of code.
