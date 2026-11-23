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

## Proposed solution — revision 2 (supersedes revision 1)

### 1. Contain the HTTP cancellation gap first

Keep the narrowly scoped, independently testable helper in `internal/api/handlers_dev_loop.go`:

```go
const devLoopSignalTimeout = 15 * time.Second

func devLoopSignalContext(parent context.Context) (context.Context, context.CancelFunc) {
    return context.WithTimeout(context.WithoutCancel(parent), devLoopSignalTimeout)
}
```

Use this around the approve/abandon Temporal signal operations after the durable decision (where applicable). Always call cancel; never spawn an unbounded goroutine. Preserve existing error mappings and audit, and report `decision persisted / delivery not confirmed` rather than implying the decision failed. Abandon retains its run-bound signal semantics. This containment by itself does **not** authorize enabling the recovery sweeper.

### 2. P1-1: prove and pin the *specific* Temporal run

Today `internal/temporalclient/client.go:264-269` calls `SignalWorkflow(ctx, workflowID, "", ApproveSignalName,...)` — empty run ID targets the latest run. `SignalAbandon` already demonstrates run-pinned signalling. The new recovery interface SHALL use a separate method such as:

```go
SignalApproveToRun(ctx context.Context, workflowID, runID string, payload map[string]string) error
```

This implementation MUST call `temporal.SignalWorkflow(ctx, workflowID, runID, ApproveSignalName, payload)` with a non-empty runID. Reject empty run IDs in the adapter and at the API caller; no implicit fallback to the old unpinned `SignalApprove`.

Establish ownership from the canonical execution row and its **immutable** `EngineRef`: canonical MCTL agents normally attach `<workflow_id>#run_<run_id>` to their own `we_`. Use the existing `parseTemporalRef` and allow only `pinned == true`, `engine == temporal`, `execution_id == grant.ExecutionID`, and a currently open execution. Verify the exact run id by `DescribeDevLoopRun(workflowID, runID)`. For a bare workflow id or `#xr_` engine ref, *do not infer* the run from latest: skip with `run_identity_unproven`, log/metric and require a separately reviewed source-of-truth fix. No silent backfill from latest-run observations.

Race safety: Describe is a liveness read, **not** a fence. The run ID on the subsequent **signal itself** is the fence: after old run closes, Temporal returns NotFound or fails rather than routing to a new run with the same workflow ID. ContinueAsNew gets a different run id and is also fenced. Record and test actual `RunID` returned by Describe equal to the persisted run id. The authenticated manual retry path must use this same exact-run dispatcher. Do not change historical direct-approve behaviour silently; route decided-grant retries through the new pinned path, and separately review any direct approve API migration.

### 3. P1-2: grant-level authorization, content and temporal execution gate

An `approved, unconsumed` row is an **intent to deliver**, not final permission by itself. Required delivery tuple:

`(grant.ID, grant.ExecutionID, grant.ActionKind, grant.Target, grant.IntentHash, grant.DecidedContextDigest, grant.ArtifactHash, workflowID, runID, current proposal content digest, current approval attempt)`.

Candidates must be `mctl-agents-approve`, decided by a human, `approved`, without `consumed_at`, `expires_at > now`, and (`fresh_until IS NULL OR fresh_until > now`). The default `FreshFor` is governed by `h.maxDecisionAge()` (24h default, configurable): no assumption that `expires_at` alone is spendability.

At **claim time**, use an authoritative store read (row lock in transaction), compare the exact grant with the **newest** grant for the execution and current attempt. Revalidate digest binding using the same decision context and actual proposal content that the owner saw; read the proposal content digest from the approved source (GitOps commit/content-digest function). An unavailable current digest or malformed target, missing attempt, foreign execution, superseded grant or no pinned run must result in a typed fail-closed refusal.

At **dispatch time**, verify that the bounded durable claim still belongs to this grant and that the authoritative newest grant and proposal digest did not change. Use a fresh DB transaction/check plus a fresh source read when required; never assume the earlier snapshot is still current. Do not hold a database transaction open across the Temporal RPC. The external Temporal call and Postgres commit cannot be a single atomic transaction: narrow the race using a store fencing token and run-bound signal, and rely on the worker's current-requested-ref / CAS consume gate for final defence. Show this layered, at-least-once safety proof in tests. This does NOT imply a global exactly-once or instantaneous cross-system atomicity guarantee.

Any grant content change or new approval attempt supersedes old delivery eligibility. The reconciler may not create grants, decide MFA, flip the proposal, start implementer, or repurpose an approval for a different run.

### 4. Durable, cross-replica reconciler: ledger + fenced delivery attempts

The existing approved approval row is the durable intent source; a separate **delivery attempt/lease table** supplies cross-pod coordination. This is preferable to one in-process `lastSent` map (which permits independent pod sends). Proposed migration, with exact names/types and indexes to be reviewed against the actual store schema before implementation:

- `devloop_approval_deliveries` keyed by `approval_ref` (unique FK where feasible); stores `execution_id`, `workflow_id`, `run_id`, `attempt_number`, `lease_token`, `lease_owner`, `lease_until`, `next_attempt_at`, `last_signalled_at`, `last_result_code`, and timestamps. Never store a raw MFA challenge or secret.
- `ClaimDelivery`: in a single Postgres transaction lock eligible grant/current attempt, ensure no competing unexpired lease, and insert/update the record with a monotonic attempt/fencing token and a bounded lease; reject `next_attempt_at > now`. Use real DB time for lease expiry.
- `SettleDelivery`: update the record only with the matching token; record `signalled` as **transport accepted**, not `consumed`. Keep last result and backoff, including ambiguous timeouts. A crash leaves the lease to expire; the next replica may retry on the **same pinned run** only.
- `Pass`: keyset page eligible grants (ordered by decided_at/id), claim each, verify exact owner/run/newest grant/content, describe the specific run, signal with `SignalApproveToRun`, settle. Fail closed on DB/Temporal/GitOps uncertainty. Do not mutate a grant decision.
- Retention and cleanup: keep per-grant delivery records long enough for audit and until grant terminal/expiry; retention is separate from lease expiry. Persistent backoff is per-grant across pods, not a global lock.
- One active delivery claim per grant is enforced in Postgres. An ambiguous RPC can still cause **at least once** signalling upon lease expiry, but no new run can receive the original signal and `ConsumeActionApproval` remains atomic CAS.

If a distinct table or index is not acceptable, the proposal must return for a new review with an equivalent durable fenced-coordination proof. Do not silently degrade to memory-only deduplication.

### 5. Freshness, pagination and accurate visibility

The candidate SQL MUST additionally filter `fresh_until IS NULL OR fresh_until > now()` and validate non-empty `decided_context_digest`, `decided_at`. An explicitly typed `stale_grant` refusal/metric is distinct from `expired`.

A keyset cursor `(decided_at,id)` bounded by `devLoopRedeliverBatch` may limit each pass, but the gauge `mctl_devloop_approval_undelivered` MUST come from a separate accurate count query (matching the eligibility predicate, not merely len(current page)). Count queries that fail must not reset the gauge to zero; expose a scrape/scan error indicator. A run that processes 20 of 200 undelivered grants should still report 200.

Counter `mctl_devloop_approval_redeliveries_total{outcome}` uses a bounded static outcome enum; no grant ids or workflow ids as Prometheus labels. Structured audit includes `approval_ref, execution_id, workflow_id, run_id, attempt_no, age, result_code` and authenticated/service actor; redact secrets and challenge data.

The alert `mctl_devloop_approval_undelivered > 0 for 10m` needs a concrete owner and GitOps monitoring location. If it is a separate PR, require a tracked issue and GO; API metrics alone do not count as a deployed alert. Document distinct `decision recorded`, `signal accepted`, `grant consumed`, and `proposal accepted` statuses.

### 6. MFA recovery page and delivery-only retry

In `handleDevLoopDecideCallback`, verify the newest grant's binding, OIDC client audience, fresh sign-in and AMR as before; on `approved` plus not-consumed show **Approved — delivery not confirmed** and a CSRF-bound `redeliver` action. The challenge records the exact action it offered and the grant, original deciding principal, context digest and content digest. A consumed/in_flight/executed grant gets factual informational text; expired/denied gets no retry.

In `handleDevLoopDecideConfirm`, after validating one-time challenge, browser cookie/CSRF and currently authorized principal, **re-read** the exact bound newest grant and run/content before any Temporal operation. Use a dedicated `redeliverApprovedDevLoopGrant` delivery-only code path; never call a general decision method that might decide a pending grant. Policy for this slice: only the original deciding principal or a separately authorized recovery admin may redeliver. Audit recovery actor independently of original decider. Refuse changed/consumed/expired/denied/superseded grants, a different browser, or stale CSRF. A lost retry response never permits a spent challenge to be replayed.

The delivery-only path uses the SAME lease/pin/revalidation contract as the background reconciler. On a successful Temporal RPC show **Signal sent; consumption not yet confirmed**, never **Workflow implemented**. Render `Consumed` only if the ledger reports it.

### 7. Startup, dark release and rollback

`DEVLOOP_APPROVAL_REDELIVER_ENABLED` defaults **false**, rather than revision-1's true. Run a read-only observe/dry-run mode first with a real DB but no Temporal mutations; the claimed/grant metrics can be evaluated. A separate owner GO plus immutable deployment digest authorizes enabling sending. Existing detached approve/abandon context changes can be validated and released separately, but shall not flip on real background redelivery.

Wiring remains a bounded ticker under `rootCtx` in `cmd/api/main.go`; each pass and each Temporal signal has its own deadline; shutting down a replica releases leases by expiry (not by assuming a SIGTERM handler always succeeds). Safe rollback is the default-off switch; maintain durable records and let expired leases recover after restart. Migration rollout/rollback and monitoring must be reviewed with operational owners.

### 8. Failure tests and evidence gates

Use deterministically controlled fakes for `SignalApproveToRun` and a Postgres-backed lease harness; no sleep-only concurrency tests. Tests:

- Request-context cancellation after decision: block fake signal; cancel HTTP context; release fake from independent test barrier; verify detached signal completed and correct audit. Separately prove timeout returns a bounded error.
- Old run closes after Describe, new run starts: no old grant arrives in new run. Unpinned refs, missing run, ContinueAsNew, NotFound, terminated run, wrong workflow id, wrong execution id all fail closed.
- Newer grant replaces old grant; content digest changes before claim/after claim/before send; old run resume/abandon/restart; no stale grant delivery or grant-creation side effects.
- Freshness shorter than backoff and fresh_until expired; no redelivery; the stale metric is accurate.
- Two replicas compete for same grant: only one live lease, deterministic lease expiry/restart, delayed worker completion, stale-token settle refusal; ambiguous transport retry remains same-run.
- More than one page of undelivered grants; accurate count, error indicators and bounded metric cardinality.
- MFA retry from different principal, stale challenge, changed digest, consumed-between-render-and-confirm, no second decision, and explicit consumed vs signalled UI semantics.
- Feature off / dry-run: zero Temporal mutations; scoped GO on feature enable only.
- CI must contain real Go vet/lint, unit and Postgres lease tests; independent reviewer must inspect the final SHA. No approval before the digest of the accepted GitOps revision is re-computed.

## Alternatives and rationale

- **Only detach the signal:** useful immediate containment, insufficient for process crash/Temporal outage.
- **In-process retry map:** rejected; it is not a multi-replica coordination or replay/restart record.
- **Full transactional outbox:** acceptable alternative if grant-state source plus durable delivery lease is insufficient; requires equally strict run-binding and grant-current checks, and a separate migration review.
- **Worker polling only:** would require a separate mctl-agents release and would not fix MFA page UX; out of this slice.
- **Rolling back the human decision on RPC failure:** rejected; the signal may already have been delivered.

## Platform impact, assumptions and open gates

- **Migrations:** revision 2 *requires a reviewed durable delivery-lease schema/migration* plus any justified query index. Old revision-1 sentence claiming unconditional no migration is superseded. Validate indexes, ownership and rollback via Postgres-backed CI.
- **Scope:** mctl-api and its Postgres schema, Temporal client interface, admin decide page, metrics and startup flag; no generic MCP tools or changing money/commercial approval kinds.
- **Replica count:** unknown in deployed cluster; chart default of one is not evidence. Design is safe for N replicas and makes no one-pod assumption.
- **Human decision freshness:** configurable (default max decision age 24h), so re-check both expires_at and fresh_until.
- **Operator gates:** identify actual monitoring owner/location and obtain deploy/release GO after independent review, not as part of docs merge.
