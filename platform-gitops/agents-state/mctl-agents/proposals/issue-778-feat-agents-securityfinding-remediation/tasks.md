# Tasks: issue-778-feat-agents-securityfinding-remediation

- [ ] 0. Dependency gate: confirm mctlhq/mctl-api#774 is merged/released; capture its route names, schemas, state vocabulary and refusal codes as JSON fixtures under `tests/fixtures/security_finding_v1/` — DoD: fixtures committed and cited from `ROUTES`; no implementation before this.
- [ ] 1. `orchestrator/security_remediation/rollout.py` (`off|observe|enforce`, default off, typo -> off), modelled on `orchestrator/work_context/rollout.py` (depends on 0) — DoD: env var read only here; unit tests for every value.
- [ ] 2. `orchestrator/security_remediation/contract.py`: `Occurrence`, `RemediationAttempt`, `RevisionBinding`, `VerificationEvidence`, provider-channel strength map; strict parsing, provider text redacted via `orchestrator.redaction` (depends on 0) — DoD: round-trip and reject-unknown tests against #774 fixtures.
- [ ] 3. `orchestrator/security_remediation/client.py` `SecurityClient`, structural copy of `work_context/client.py` (auth, https-only, no-redirect, single `ROUTES` table, found/refused/unknown answers, deterministic idempotency keys) (depends on 2) — DoD: transport-monkeypatched tests for every route and for 5xx/timeout -> unknown.
- [ ] 4. `start.py` + CLI `python -m orchestrator.security_remediation start --occurrence-id`: read occurrence, call #774 start, then request execution via `WorkItemClient` so the existing dispatcher starts the DevLoop (depends on 1, 3) — DoD: active-attempt refusal produces no WorkItem/request; two occurrences produce two attempts.
- [ ] 5. Add defaulted `IssueRef.remediation_attempt_id` in `orchestrator/temporal/workflows/dev_loop.py`, carried from the execution request / dispatcher (`orchestrator/temporal/dispatcher.py`) (depends on 4) — DoD: old-history replay test passes.
- [ ] 6. Activity `bind_remediation_landed` in `orchestrator/temporal/activities/security_remediation.py`, called from `_finish_after_watch` behind `workflow.patched("security-remediation-bind")` when merged; binds `PRState.merge_commit` (+ image digest if deploy observation has one); registered in `worker.py` (depends on 3, 5) — DoD: merged PR -> bind call, no resolve call anywhere in DevLoop; closed-unmerged -> no bind.
- [ ] 7. `verify.py`: `Strategy` protocol, strategies `assurance_replay` (validates via `orchestrator.runtime_assurance`, replays via `assurance_harness.execute`, revision must equal landed SHA), `regression_test` (via `orchestrator/ci_checks.py` on landed SHA), `provider_claim` (weak); empty adapter registries for `scanner_rerun`/`manual_evidence`; pure `decide()` (depends on 2) — DoD: decision table tests for absent/present/error/timeout/wrong-revision/claim-only.
- [ ] 8. Runner: submit each evidence item and decision through `SecurityClient.submit_verification` with observation-key idempotency; bounded timeouts/attempts (depends on 3, 7) — DoD: unknown API answer writes nothing further.
- [ ] 9. Regression path: `submit_observation` forwarding with stable observation key; local refusal for pre-fix / known-non-descendant revision; ancestry unknown passed as unknown (depends on 3) — DoD: tests T9/T10.
- [ ] 10. Temporal schedule `security-verify-sweep` on the schedule-owning worker, bounded page per tick; optional inline verify after task 6 (depends on 6, 8) — DoD: schedule registered only when mode != off.
- [ ] 11. ADR `docs/adr/024-security-remediation-runner.md` and a `LLMS.md` entry — DoD: documents trust boundary, rollout ladder and #774 ownership.

## Tests

- [ ] T1. Second `start_remediation` for an occurrence with an active attempt is refused deterministically and creates no WorkItem/request/DevLoop.
- [ ] T2. Two occurrences under one finding get independent attempts, WorkItems and DevLoops.
- [ ] T3. Attempt #1 (and its verification evidence) is unchanged after a regression creates attempt #2.
- [ ] T4. Full two-cycle proof against a fake #774 server: fix A -> bind SHA A -> verification absent on A -> resolved -> regression observation on descendant -> reopen -> attempt #2 -> fix B -> bind SHA B -> verification on B -> resolved.
- [ ] T5. Merge without verification leaves the occurrence `awaiting_verification`; grep-style test asserts DevLoop code never calls a resolve route.
- [ ] T6. Verification bound to a different SHA/artifact is rejected locally and never submitted as resolving evidence.
- [ ] T7. error / timeout / budget exhaustion / adapter unavailable -> `unverifiable`, never `resolved`.
- [ ] T8. Provider `fixed` claim alone does not resolve under default policy.
- [ ] T9. Stale scan bound to the pre-fix revision cannot reopen a resolved occurrence; a different SHA with unknown ancestry is not treated as descendant.
- [ ] T10. Redelivered regression observation uses the same observation key and counts once toward the confirmation threshold.
- [ ] T11. Runtime Assurance replay counts at its configured strength only when finding/run/result validate and the source channel is authenticated; a forged or mismatched binding does not count.
- [ ] T12. Hostile provider title/severity/suggested-fix (including injected instructions and credentials) has no effect on strategy selection, decision or transition, and is redacted in logs.
- [ ] T13. Every write goes through `SecurityClient` with the mctl-agent principal and logs attempt/evidence ids; API unknown writes nothing.
- [ ] T14. Rollout `off` makes zero HTTP calls; `observe` makes reads only.
- [ ] T15. DevLoop history recorded before this change replays without nondeterminism.

## Rollback

Set `SECURITY_REMEDIATION_ROLLOUT_MODE=off` on `admins/mctl-agents-worker`
(gitops) to stop all #774 calls and the sweep immediately; in-flight DevLoops
skip the bind activity body. If code must be reverted, keep the
`workflow.patched("security-remediation-bind")` marker and the defaulted
`IssueRef.remediation_attempt_id` field so running histories still replay.
No data is stored in mctl-agents, so nothing needs cleaning; occurrences left
`awaiting_verification` remain valid in #774 and can be verified once
re-enabled.
