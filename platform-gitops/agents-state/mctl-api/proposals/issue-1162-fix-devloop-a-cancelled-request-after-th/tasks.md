# Tasks: issue-1162-fix-devloop-a-cancelled-request-after-th

Revision 2 — reconciled with independent evidence-based review 2 P1 / 6 P2 on mctl-api#1162. These tasks are **proposal only**. No checkbox is implementation evidence; no approval or implementer GO is inferred.

## Implementation sequence and acceptance gates

- [ ] **R0. Fix the execution/run authority model (P1-1).** Trace how the canonical mctl-agents attaches an execution with `engine_ref=<workflow>#run_<run_id>` and how `parseTemporalRef` reads it. Explicitly require a persisted non-empty concrete runID and bind approval_ref to execution_id and that run. Define fail-closed behavior for workflow-only or `#xr_` engine refs; no "latest run" fallback or best-effort backfill. — DoD: source-pinned execution/grant mapping and deterministic tests for missing/mismatched run evidence.

- [ ] **R1. Bounded detached signal containment (original #1, P2-5).** Implement `devLoopSignalContext` with `context.WithTimeout(context.WithoutCancel(parent),15s)` for approve and abandon after durable decision, retaining 404/502/503 mapping/audit. Preserve abandon's existing explicit runID. Audit decision-persisted vs signal-ack states separately. — DoD: no direct `r.Context()` passed into either Temporal signal; cancellable-browser and separate deadline tests pass.

- [ ] **R2. Run-pinned approve client API (P1-1).** Introduce `SignalApproveToRun(ctx,wf,runID,approval_ref)` on the DevLoopClient adapter and fake Temporal client. Refuse empty runID and use `SignalWorkflow(ctx,wf,runID,...)` rather than `""`. Replace reconciler and approved-grant retry callers with this method, without silently redirecting old direct-approve behavior. — DoD: old run closes/restarts between Describe and Signal; new run receives zero old-grant signals.

- [ ] **R3. Durable grant-current / digest eligibility gate (P1-2, P2-1).** Implement a read/claim-time and dispatch-time gate against the *newest* grant for the exact execution and attempt. Match human decision, `decided_context_digest`, intent hash/target, `artifact_hash`, current proposal content digest, execution/run binding, state approved and unconsumed, `expires_at` and optional `fresh_until`. Source digest retrieval failure must refuse delivery. Neither the reconciler nor retry may decide/create grants or flip proposal state. — DoD: Postgres and fake-GitOps tests for supersession, changed content, fresh_until, loss of GitOps access and closed/restarted executions.

- [ ] **R4. Durable delivery coordination and migration (P2-2, P3 migration).** Use approved ledger rows as intent and create a narrowly scoped `devloop_approval_deliveries` attempt/lease table, keyed by grant ID, with immutable target run and bounded owner/fencing token, lease expiry, retry-at, attempt counter and last result. Implement DB-atomic `ClaimDelivery`/fenced `SettleDelivery`, no DB transaction held across RPC; use DB time. Confirm query indexes and migration rollback. — DoD: two different reconcilers never both hold active claim; stale lease owner cannot settle; new pod recovers after lease expires. Never assert exactly-once transport.

- [ ] **R5. Safe background reconciliation (original #2-3, both P1).** Implement `UndeliveredActionApprovals` with keyset pagination and the freshness predicate; each candidate passes R0/R3/R4, exact-run Describe and R2 run-bound delivery. Handle closed/unresolved/Unknown run, newer grant, digest mismatch, lost lease, ambiguous result, retries/backoff with typed outcomes. — DoD: no old grant in any new run, no stale grant delivery under negative tests, and durable recovery after crash/restart.

- [ ] **R6. Authenticated MFA retry without deciding again (P2-3).** Update `handleDevLoopDecideCallback` to present approved-but-unconsumed as delivery-not-confirmed; separate challenge action `redeliver`. In confirm, re-check actor policy (original decider or explicitly privileged recovery admin), MFA provenance, newest grant/content/run, CSRF/cookie/challenge and freshness. Call a delivery-only R3/R4/R2 service, not generic `DecideActionApproval`. A consumed grant gets an informational state, not a button. — DoD: no new `action_approval.decision` rows/audits from redelivery; same-grant run-pinned signal only; race/identity tests pass.

- [ ] **R7. Complete telemetry, paging and alerts (P2-4).** Add authoritative count query for all eligible undelivered grants, independent of limited pages; gauge cannot silently go zero after read errors. Add bounded outcome counters and audit with run ID + grant ID + attempts (no sensitive data). Identify exact monitoring owner/path for `mctl_devloop_approval_undelivered > 0 for 10m`, or open a separate explicitly gated alert issue and record it as unshipped. — DoD: >1-page test, failed-query test, bounded label assertions and Prometheus exposure test.

- [ ] **R8. Dark enablement and rollback (P2-6).** Gate background sends on `DEVLOOP_APPROVAL_REDELIVER_ENABLED=false` by default; include observe-only mode and no-send proof before live enablement. Wire a bounded `rootCtx` ticker in `cmd/api/main.go`, rollout flag/docs in Helm/README, metric verification and a separately authorized production enablement playbook. — DoD: feature OFF performs zero Temporal mutations; only owner GO on image digest may enable; rollback stops new sends without erasing grant/lease history.

- [ ] **R9. Consistency, CI and independent release gates.** Run format, vet, lint, build, Go unit/integration suites and real Postgres-backed schema/lease tests. Confirm negative tests, API authorization, no new MCP tools and no changes to Glovo/deploy/release-window semantics. Pin CI head SHA, request independent Claude and Agy reviews, classify P1/P2/P3 and fix blockers before an implementation PR merge. After docs-only merge, recompute official GitOps proposal digest and require fresh human MFA approval for that exact digest. — DoD: approval/release GO only after all required gates are evidenced.

## Deterministic test matrix

- [ ] **T1 HTTP cancellation:** fake signals barrier on entry; cancel browser context independently; release fake, require detached success/audit. Reverse the helper and prove the test fails. Separate deadline expiry for both approve/abandon; no hanging fake.
- [ ] **T2 Run fence:** `Describe(run-old)` then close old/start new before `SignalApproveToRun(run-old)`; new receives nothing. Also reject unpinned workflow-id, `#xr_`, wrong run, ContinueAsNew, NotFound, terminated and Unknown statuses.
- [ ] **T3 Grant supersession:** older approved/unconsumed followed by a new pending or approved newest grant; old is never sent. Change content digest/approval attempt after claim and immediately before dispatch; old is fenced.
- [ ] **T4 Freshness:** expired expires_at; stale fresh_until with non-expired grant; configured decision freshness shorter than retry/backoff; no signal, typed result.
- [ ] **T5 Recovery after crash:** grant committed approved, signal absent; new process/replica queries durable state, leases and safely resends exactly bound ref/run after lease expiry, then grant consumed. No new MFA decision.
- [ ] **T6 Cross-replica race:** two reconcilers contest the same grant; one active lease; stale lease-token settlement fails. Crash mid-signal and ambiguous RPC cause at-least-once retry only to same pinned run.
- [ ] **T7 Outage fail closed:** DB timeout, GitOps digest unavailable, malformed execution ref, unknown Temporal status, closed run, describe failure, stale caller: zero sends, observable typed refusal.
- [ ] **T8 Pagination and metrics:** at least 21 eligible grants with page size 20; gauge reports 21; scan error does not report misleading zero; counters have fixed low-cardinality labels.
- [ ] **T9 Retry happy path:** already-approved signed-in original decider, fresh CSRF/MFA, exact digest/run, one explicit redelivery, no `DecideActionApproval` invocation. "Signal sent" is not "consumed".
- [ ] **T10 Retry negative:** pending, consumed, denied, expired, superseded, wrong actor, wrong OIDC audience, wrong MFA AMR, cross-browser cookie, stale CSRF/challenge, consumed between GET and POST, changed digest and run.
- [ ] **T11 Feature OFF and observe:** background sweeper default OFF or dry-run emits no real Temporal writes even with eligible grants; switching ON requires separate GO.
- [ ] **T12 Regression:** no duplicate implementer, no double grant consumption, no human impersonation; worker current-grant gate still protects canonical runs.

## Deployment and rollback prerequisites

- Docs revision 2 is proposed through the **existing proposal directory** in a review PR. Do not edit `.status.yaml` or claim approval based on docs changes.
- Prior to enabling, assess schema migration/index on staging with actual Postgres and roll it back independently. Default OFF remains after code deploy.
- If delivery fails, disable `DEVLOOP_APPROVAL_REDELIVER_ENABLED` and investigate durable lease/attempt rows; do not remove grant decisions. Containment helper can be separately reverted if required.
- Before any implementer run, a reviewer must confirm **both P1 and all six P2** in this revision were resolved, request independent fresh review, and obtain a new owner MFA decision bound to the accepted proposal digest.
