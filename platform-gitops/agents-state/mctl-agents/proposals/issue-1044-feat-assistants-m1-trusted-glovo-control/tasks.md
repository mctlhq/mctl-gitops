# Tasks: issue-1044-feat-assistants-m1-trusted-glovo-control

- [ ] 1. Create `orchestrator/assistants/contracts.py` and `ids.py` (`SCHEMA_VERSION`, `GlovoControlInput`, `GlovoControlResult`, activity I/O types, `control_workflow_id`, `command_id`) — DoD: validators reject unknown fields, unknown `schema_version`, over-length strings, malformed refs and any `hir_` field; ids are deterministic and pure.
- [ ] 2. Add `tools/assistants_schema.py` and commit `orchestrator/assistants/schemas/glovo-control-{input,result}.v1alpha1.json` with `SHA256SUMS` (depends on 1) — DoD: regeneration is byte-identical; a test fails on drift.
- [ ] 3. Create `orchestrator/assistants/ports.py` (`ControlApiPort`, `ProviderBridgePort`) and `api_client.py` (HTTP client on `MCTL_ASSISTANTS_TOKEN`, no redirects, route constants mirroring mctl-api#953/#954 proposals) (depends on 1) — DoD: client refuses to construct when only `MCTL_TOKEN` is present; every method returns typed enums, never raw provider data.
- [ ] 4. Create `orchestrator/assistants/bridge.py` and `bridge_decision.json` (`BLOCKED_FOR_INTEGRATION`) (depends on 3) — DoD: `load_bridge("real")` raises `BridgeBlocked`; no Nexus endpoint, no cross-namespace Activity, no provider-to-control signal exists in the package.
- [ ] 5. Create `orchestrator/assistants/activities.py` (`revalidate_scope`, `resolve_connection`, `quote_fake_basket`, `request_order_approval`, `read_approval`, `create_provider_command`, `read_provider_result`, `request_provider_cancel`, `release_reservation`) over the ports, with `intent_hash` from `orchestrator.action_approvals` (depends on 3, 4) — DoD: activities return ids/enums/bounded refs only; transient errors retry with bounded policy; unknown answers surface as not-live.
- [ ] 6. Create `orchestrator/assistants/workflow.py` `GlovoControlWorkflow` with the state machine, id re-derivation, immutable fingerprint/consent binding, periodic and per-transition revalidation, signals `assistants_approval_decided` / `assistants_provider_result` (ids only), bounded waits, non-resurrecting cancellation, `unknown` without re-dispatch (depends on 5) — DoD: workflow sandbox passes; every terminal path returns a valid `GlovoControlResult`.
- [ ] 7. Create `orchestrator/assistants/worker.py` (namespace `mctl-assistants` required with no default, queue `mctl-assistants-control`, refuses `MCTL_TOKEN` and provider credential env, explicit slot limits, no schedules or dispatcher, `BLOCKED_FOR_INTEGRATION` exit for real bridge) (depends on 6) — DoD: `python -m orchestrator.assistants.worker` with wrong namespace exits non-zero before connecting.
- [ ] 8. Add `Dockerfile.assistants-control` (digest-pinned python:3.12-slim, `uv sync --locked --no-dev`, minimal copy, non-root) (depends on 7) — DoD: two builds from the same commit give the same layer digests for the app layer; image has no `claude_agent_sdk`, `gh`, `node`, `go`.
- [ ] 9. Add `tests/assistants_harness.py` (disposable `start_local` server with `mctl-assistants` and decoy `mctl-agents`, fake `ControlApiPort` with two tenants and two users, test-only `LocalFakeBridge` with write counter) (depends on 6) — DoD: harness used by T3-T14 and tears down its server.
- [ ] 10. Add CI job `assistants-control-build` to `.github/workflows/pr-validation.yml` (build image, run import check and namespace-refusal check in the image, uid check) (depends on 8) — DoD: job green on the PR; existing `docker-build` job and `release-please.yml` unchanged.
- [ ] 11. Add `docs/adr/026-assistants-control-workflow.md` documenting contracts, id derivation, the bridge gate and the explicit non-goals (depends on 6) — DoD: ADR links #1043, #953, #954, #2456, #2457, .github#324 and states activation requires a separate GitOps approval.

## Tests

- [ ] T1. Contract tests: round-trip, unknown field, unknown `schema_version` -> `contract_version_unsupported`, over-length strings, `hir_` field rejected; committed schema hash matches regeneration.
- [ ] T2. Import isolation (subprocess, like `tests/test_worker_isolation.py`): `orchestrator.assistants.worker` imports none of `claude_agent_sdk`, `orchestrator.auth`, `orchestrator.run_implementer`, `orchestrator.temporal.workflows`, `orchestrator.temporal.worker`, `orchestrator.temporal.mctl_client`; and `orchestrator.temporal.worker` does not import `orchestrator.assistants`.
- [ ] T3. Happy path: resolve -> quote -> `aar_` approved -> one command -> result -> `completed`; fake write counter == 1.
- [ ] T4. Worker refuses `TEMPORAL_NAMESPACE` unset, `mctl-agents`, `kuptsi`; refuses `MCTL_TOKEN` set; registers only assistants types; creates no schedule (asserted via schedule list on the dev server).
- [ ] T5. Structural cross-namespace denial: static scan of `orchestrator/assistants/` finds no `Client.connect` except in `worker.py`, no `start_workflow`, `signal`, `query`, `list_workflows`, `terminate`, `get_workflow_handle`; on the dev server, no workflow appears in decoy `mctl-agents` after the full suite. Live authorizer denial is marked deferred to #2456/#2457.
- [ ] T6. Workflow id mismatch (input scope differs from id) -> `failed/workflow_id_scope_mismatch`, zero activities beyond validation.
- [ ] T7. Two tenants and two users in one tenant: running four workflows concurrently, each fake API call and bridge command carries only its own refs; a result signalled with another workflow's `command_id` is ignored; no result field leaks another order's ref.
- [ ] T8. Stale install revision and revoked `gcn_` at each phase (before quote, while awaiting approval via periodic revalidation, just before dispatch) -> `refused`, write counter 0.
- [ ] T9. mctl-api unavailable during revalidation -> no transition, bounded retry, never dispatch on unknown.
- [ ] T10. Approval paths: denied, expired, already consumed, fingerprint changed between quote and dispatch -> no dispatch; a `hir_` answer alone never leads to dispatch.
- [ ] T11. Idempotency: activity retry of `create_provider_command` reuses the same `command_id`; duplicate result signal is a no-op; worker restart mid-settle (replay) produces no second command.
- [ ] T12. Cancellation before approval, after approval before dispatch, and after dispatch: no new command after cancel; only `request_provider_cancel`/`release_reservation` run; a cancelled workflow never calls resolve/approve again; revoked connection stays revoked in the fake.
- [ ] T13. Provider `unknown` -> `order_status=unknown`, no re-dispatch; settle timeout -> `expired`.
- [ ] T14. Tenant cap: `tenant_cap_reached` from revalidation/admission -> `refused`, write counter 0.
- [ ] T15. Bridge gate: `load_bridge("real")` raises `BridgeBlocked`; worker with `ASSISTANTS_BRIDGE=real` exits reporting `BLOCKED_FOR_INTEGRATION`.
- [ ] T16. Safety scan: no `glovo.com` URLs, no cookie/session handling, no `checkout|charge|payment` operations in `orchestrator/assistants/`.
- [ ] T17. Replay: record histories for T3, T8 and T12 and replay them with `Replayer` (as in `tests/test_workflow_replay.py`).

## Rollback

Everything is additive and undeployed: revert the PR (new package, Dockerfile,
schemas, harness, ADR and the one new CI job). No namespace, service, schedule,
image tag or gitops path references these files, and the DevLoop worker, queues
and release dispatch are unchanged, so a revert has no runtime effect. If a
later activation (#2457) misbehaves, its rollback is removing that GitOps
deployment; this code needs no change for it.
