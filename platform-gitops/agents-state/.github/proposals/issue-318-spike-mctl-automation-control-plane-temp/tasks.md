# Tasks: issue-318-spike-mctl-automation-control-plane-temp

- [ ] 1. Pin and read sources for D1: the mctl-agents `orchestrator/temporal/worker.py` and its schedule utilities; the mctl-api Temporal client, MCP tool registry, WorkItem, execution-request and usage-ledger handlers; mctl-telegram AssistantInstall and managed runtime (#1002, #1088, #1092); mctl-support task store and admission (#243); mctl-agents#757 attention routing; and #41/mctl-api#284 and #300 status. — DoD: an evidence-pins table with 40-hex SHAs per repo, and each component marked deployed, flagged, planned or `unknown (not observed)` with a source link. mctl-api and mctl-telegram runtime state stays `unknown (not observed)` unless an operator read is obtained.
- [ ] 2. Write D1, the existing-components and overlap/ownership map, in `docs/spikes/automation-control-plane.md` (depends on 1). — DoD: one table that names the canonical store and owner per primitive and the duplicates to avoid (second scheduler, second run store, second identity key), and explicitly states the #41 Task-vs-automation and #306 `wi_` reuse boundaries.
- [ ] 3. Write D2: the AutomationDefinition v0 and AutomationRun contract, trigger specs (`at`, `schedule`, `event`, `dependency`), the event-trigger binding to `events/schemas/event-envelope.v1.schema.json`, MCP/REST schemas for the nine operations, a closed error vocabulary, and the threat model (depends on 2). — DoD: JSON schemas embedded or placed under `docs/spikes/automation-control-plane/schemas/`. Every mutation has an idempotency key, and updates take `expected_version`. Raw Temporal fields are rejected. DST, overlap, catch-up, dedupe and the Start-vs-Signal rules are stated.
- [ ] 4. Write D3: Mermaid sequence diagrams for create, update/pause, trigger, revoke, recover, inspect and deliver across Claude, ChatGPT and Telegram; the permission matrix covering owner, assistant, support, admin and system; and the cost matrix (depends on 3). — DoD: the same `automation_id` appears across all three surfaces in the diagrams, the support row is tenant-bound, read-only and TTL-bounded, and system schedules are separated from user schedules.
- [ ] 5. Build the Go reference model in `docs/spikes/automation-control-plane/` (`go.mod` with `module mctl.ai/spikes/automationcp`, `go 1.22`, stdlib only): `model/` (clock, store, scheduler, verifier, router, checkpoint, ledger, delivery), `fixtures/*.json`, `harness_test.go`, `negative_test.go` and `bench_test.go` (depends on 3). — DoD: `go vet ./... && go test ./...` passes offline, and every test in the Tests section exists and is named after its fixture.
- [ ] 6. Add a CI step to `.github/workflows/workflow-tests.yml` after the MCP gateway G0 step: setup-go with `go-version-file: docs/spikes/automation-control-plane/go.mod` and run `go vet ./... && go test ./...` there; add the module path to the workflow's `paths` filters (depends on 5). — DoD: the workflow runs the new step on PRs that touch the module.
- [ ] 7. Write D4, the measured evidence: refusal counts per negative fixture, idempotency results, fake-clock scheduling accuracy, recovery after a simulated worker crash, and spend and delivery accounting (depends on 5). — DoD: every number is labelled as model evidence, and a list names the Temporal behaviours that remain unproven against a server.
- [ ] 8. Write D5: the A/B/C/D comparison, a technology scoring table (mctl-api Go SDK plus MCP, mctl-agents Python utilities, official read-only temporal-mcp, community Python MCP, TypeScript HTTP MCP), exactly one proposed outcome, an ownership map, rollout and rollback proposals, operational and cost targets, the Telegram delivery outcome, and ChatGPT push marked `unknown` per #300 (depends on 2, 4 and 7). — DoD: one outcome is proposed, follow-ups are listed as unfiled candidates with duplicate-check targets, and the text says owner decision pending.
- [ ] 9. Add `roadmap/spikes/automation-control-plane.yaml` (lifecycle `proposed`, issue mctlhq/.github#318, four outcomes, `timebox.decisionBy: 2026-12-15`, `execution.devloop: true`, `evidence.report`, no `epic` and no `decision`) and add an `AGENTS.md` `# Spikes` entry (depends on 8). — DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes.

## Tests

- [ ] T1. `TestAtOnceFiresExactlyOnce`: an `at` trigger at 09:00 Europe/Berlin fires once under the fake clock, and a restart of the model does not refire it.
- [ ] T2. `TestAtDSTGapAndOverlap`: a nonexistent local time shifts forward and an ambiguous time takes its first occurrence, as the contract states.
- [ ] T3. `TestScheduleRecurrenceOverlapSkip` and `TestScheduleCatchupWindow`: a weekly cron in a timezone fires at the expected instants. A long-running run causes the next fire to be skipped (default policy). Misfires inside the catch-up window run once, and misfires outside it are dropped.
- [ ] T4. `TestSignedWebhookStartsRun` and `TestDependencySignalsAwaitingRun`: a valid HMAC GitHub-style delivery becomes envelope v1, passes the allowlist and starts a run. A dependency template receives a Signal instead.
- [ ] T5. `TestSupportFollowupBounded`: the support actor creates `support.diagnostic-followup.v1` for its bound tenant. The run is read-only, and creation expires after TTL or after 3 fires. A mutating template from support is refused.
- [ ] T6. `TestForgedEventRejected`: a bad signature is refused with `signature_invalid` and no run starts.
- [ ] T7. `TestReplayAndDuplicateDeduped`: a stale timestamp is refused with `replay_window`, and a duplicate envelope `id` yields one run and one budget reservation.
- [ ] T8. `TestBurstOverlapCapped`: a burst of N events against a definition with fanout cap K yields at most K runs, and the rest are coalesced or refused with `fanout_capped`.
- [ ] T9. `TestCrossTenantInspectAndCreateRefused`: tenant B cannot get, list or create on tenant A, and gets not-found semantics.
- [ ] T10. `TestRevokedInstallFencedAtFire`: an install revoked after creation causes the next fire to be refused at the checkpoint, and repeated refusals auto-pause the definition.
- [ ] T11. `TestBudgetExceededRefused`: a reservation over the per-run or per-owner ceiling refuses before the agent mock is called.
- [ ] T12. `TestWorkerCrashRecovers`: a crash after reserve and before settle resumes on the same `we_` without a double reservation.
- [ ] T13. `TestDeliveryFailureRecorded`: when the Telegram adapter fails, retries are bounded, the result is marked `delivered: failed` and stays readable.
- [ ] T14. `TestRawTemporalWorkflowRefused`: a create carrying `workflow_type`, `task_queue`, `namespace` or `signal` is refused with `raw_temporal_forbidden`.
- [ ] T15. `TestDeleteDoesNotTerminateInFlight`: deleting during a run stops future fires, and the in-flight run finishes unless `cancel_in_flight` is set.
- [ ] T16. `TestIdempotentCreateAndOptimisticUpdate`: the same idempotency key returns the same `au_`, a reused key with different arguments returns `idempotency_key_reused`, and a stale `expected_version` returns `version_conflict`.
- [ ] T17. Run `roadmap/scripts/validate.py` on the new manifest; `roadmap/scripts/lifecycle_guard.py` accepts the proposed lifecycle.

## Rollback

All changes are documentation, a manifest, an isolated Go module and one CI
step in `mctlhq/.github`. Revert the PR. No production state, schedule, flag
or GitOps value is touched, so nothing else needs undoing. If the new CI step
alone misbehaves, remove that step from `.github/workflows/workflow-tests.yml`
and keep the report. If the owner rejects the spike's direction, set the
manifest lifecycle through the normal owner-reviewed roadmap change, not by
deletion.
