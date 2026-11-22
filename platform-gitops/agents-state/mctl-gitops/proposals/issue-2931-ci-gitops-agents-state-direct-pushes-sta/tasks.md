# Tasks: issue-2931 — revision 2 (design-only GO; implementation gated)

**State:** all tasks are proposed, not authorized to execute by this document. `GO_RESEARCH / DESIGN` permits evidence and amendment; `GO_IMPLEMENT`, `GO_MERGE`, production credential/repository changes and a live cutover require separate owner decisions. Same issue and proposal, no duplicate.

## Stage 0 — evidence and architecture gates

- [ ] 0.1. Snapshot code/CI/ruleset and pin revision SHAs of `mctl-gitops`, `mctl-agents`, `mctl-api`. Confirm #2931 evidence, queue rebuilds, duration histograms, GitHub-hosted job saturation and relationship to #2935. DoD: source-pinned evidence matrix with observed vs inferred claims.
- [ ] 0.2. Complete exhaustive state-reader/writer inventory using code search and runtime configuration for each CWFT (investigate, implement, approve, shepherd, reconcile, run, incident responder), `mctl-api` reader/decide/MCP handlers and `mctl-agents` Temporal activities/CLI. DoD: path+line+owner, legacy contract, target contract, test for every consumer; unknown blocks implementation.
- [ ] 0.3. Verify new repo `specs`/`runtime` protection topology in isolated canary against actual GitHub plan, rulesets and App/deploy-key identity. DoD: negative push test to `mctl-gitops/main` and protected `specs` using state-writer identity; credential privilege diff linked to #2543; choose equivalent secure architecture if test fails.
- [ ] 0.4. Define versioned locator, proposal identity, immutable review ref, content digest and grant/transition schemas, plus an epoch and replay policy. DoD: explicit schemas, compatibility matrix, digest/test vectors, deny paths for missing/stale grant and denied implementer.
- [ ] 0.5. Build a no-mutation migration runbook with snapshot/backfill, parity, active DevLoops, pending decide grants, CAS conflict behavior, rollback and GO_CUTOVER checklist. DoD: signed-off safety criteria and fail-closed boundary cases; no assumed auto-approval.

## Stage 1 — separately authorized implementation slices

- [ ] 1.1. New repo provisioning and permissions: owner-approved state repo, protected spec-review path and runtime-only bot identity; provision secret delivery and audit. DoD: scope assertions and deny tests, no access to GitOps main. Depends: 0.3, separate owner GO.
- [ ] 1.2. Reviewable spec candidate path: investigator-generated `requirements.md` / `design.md` / `tasks.md` / `proposed-content.md`, immutable revisions and reviewed PR amendment flow. DoD: unreviewed spec cannot be consumed as executable; re-amendment revokes old grants. Depends: 0.4, 1.1.
- [ ] 1.3. Durable runtime store and CAS writer: status/attempts/human-input/inbox, idempotent transition journal, bounded conflict/retry handling and no implicit GitOps fallback. DoD: concurrency + race tests, permanent error surfaced. Depends: 0.4, 1.1.
- [ ] 1.4. Redirect every producer (six CWFT paths, incident responder and any found in 0.2) to versioned locator and branch-scoped writer. DoD: isolated harness proves producer identity, status idempotency and no GitOps main commit. Depends: 1.3.
- [ ] 1.5. Redirect every consumer (Temporal `gitops_state.py`, other proposal/PR activities, mctl-api reader and decide, CLI, API/MCP documentation and validators) with shadow comparison flag. DoD: parity and approval freshness tests; no reader silently uses wrong repo or ref. Depends: 1.2–1.4.
- [ ] 1.6. Rebind approval digest and human authority to immutable spec commit + target state record. DoD: existing 4-file digest vectors match across implementations; stale/missing/anonymous/moved grant blocked, MFA decide binding proven, no duplicate implementation. Depends: 1.2–1.5.
- [ ] 1.7. Implement read-only Merge Queue + hosted-runner watcher with causal evidence, 3+ rebuild threshold, 15-min no-progress, bot push invalidation, 5-min evaluation, deduplicated delivered alert and monitoring-degraded signal. DoD: live-read API schema/scope fixture, tests and an operator route; no write secrets. Depends: 0.1, 0.3.
- [ ] 1.8. Add new repository's validators and GitOps CI audit guard; coordinate related `mctl-gitops#2935` stale push-run cancellation without reimplementing its changes here. DoD: CI proves approval records, allowed paths, reader contract, forbidden direct GitOps pushes, bounded hosted-runner demand.

## Stage 2 — controlled migration (requires owner GO_CUTOVER)

- [ ] 2.1. Backfill and compare file manifests, content digests, status histories and in-flight grants at pinned SHA. DoD: zero unexplained mismatches and checkpoint usable for recovery. Depends: 1.1–1.6.
- [ ] 2.2. Enable shadow reads, test synthetic concurrent writes/approvals, observe parity and telemetry; keep prod writers unchanged. DoD: explicit freshness and replay metrics, recovery exercise. Depends: 2.1.
- [ ] 2.3. Operator-approved writer cutover after controlled quiesce/drain, final snapshot, lease/epoch switch, revocation of old writing path and versioned locator activation. DoD: no lost/duplicated statuses, old approval links fail closed or resolve explicitly, zero direct bot agent-state commits to GitOps main. Depends: 2.2 and explicit owner GO_CUTOVER.
- [ ] 2.4. Post-cutover pressure test + negative authorization test and queue-runner metrics. DoD: representative DevLoop burst leaves Merge Queue progressing, canceled stale jobs don't exhaust shared slots; monitoring and recovery alerts delivered. Depends: 2.3.
- [ ] 2.5. Retire P6 deploy key/bypass with `#2543` and unused GitOps validators only after equivalent new guards proven; document operator runbook/rollback. DoD: revocation audit and no dangling writers. Depends: 2.4.

## Tests and release gates

- [ ] T1. Static contract tests: all producers/consumers use versioned locator; no active `git push origin HEAD:main` in agent-state workflows; no code path allows implicit legacy production fallback.
- [ ] T2. Digest vectors: absent vs empty proposal files; byte-exact content digest; amend-after-grant; old SHAs; wrong proposal; missing approver; concurrent duplicate signal; accepted-noop only for exact authorized repeat.
- [ ] T3. CAS/migration: simultaneous writer conflict, rebase, status transition race, retry exhaustion, network 403/404/429/5xx, partial backfill, schema/version skew, delayed old-writer replay.
- [ ] T4. Permission proof: state writer cannot push `mctl-gitops/main` or `mctl-agents-state:specs`; bot cannot force-push or remove protection; CI and audit reject forged approval.
- [ ] T5. Monitor unit/fixture: empty, healthy but slow queue, 3 rebuilds, 15-min no progress, invalidating bot commit, missing SHAs, API pagination/outage/rate limiting, delayed scheduled job, actionable alert attribution and recovery.
- [ ] T6. Hosted-runner and queue integration: synthetic high-volume agent writes, `validate` push-run cancellation behavior (#2935), steady queue progress and no org-wide job starvation.
- [ ] T7. Controlled cutover + rollback drill: source/target parity, active approval, pending decide link, amended proposal, consumed grant, in-flight implementation, partial cutover; no unapproved work and no unsafe direct GitOps fallback.

## Document revision and independent review (this authorization only)

- [x] D1. Reframe existing `requirements.md`, `design.md` and `tasks.md` around selected separate-repository option + monitoring; preserve linked #2931, #2543, #2935.
- [ ] D2. Commit docs-only changes in an isolated PR to `mctl-gitops/main`. No `.status.yaml` edit, no approval, no implementer, no queue bypass.
- [ ] D3. Obtain *independent* Claude/Agy or separate reviewer evidence-based critique of **exact PR HEAD SHA**: classify P1/P2/P3, check real path/line claims and unresolved questions, verify no authority leak and docs scope. Author self-check is not a substitute.
- [ ] D4. Address blocking review findings in the same PR, rerun reviews/checks on new HEAD, then **separately** seek owner permission before docs-only merge through normal Merge Queue. Even merged docs do not grant proposal approval or implementation.
- [ ] D5. After future docs-only merge recompute reviewed content digest and ensure `.status.yaml=proposed`; any future GO_IMPLEMENT is bound to the reviewed revision and a separately authorized bounded slice.

## Rollback by phase

- Pre-cutover: stop, leave old writers intact; restore docs via PR and close experimental canary. No permissions expanded.
- Shadow: disable shadow consumers, discard temporary state after verified snapshot; do not touch production approval.
- Post-cutover: **hold writes and implementations**, reconcile status/grants from durable source at a pinned epoch, explicitly reauthorize switch to the verified target. Do not automatically enable bypass writes to GitOps main. If parity or digest cannot be proven, fail closed and obtain new owner decision.
