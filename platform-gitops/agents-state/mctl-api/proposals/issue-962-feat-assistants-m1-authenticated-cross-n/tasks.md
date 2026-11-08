# Tasks: issue-962-feat-assistants-m1-authenticated-cross-n

- [ ] 1. Vendor pinned schemas. Add `command.schema.json` and `result.schema.json` from mctl-agents#1043 into `internal/bridge/schema/`, with `PROVENANCE` (upstream repo, commit, sha256), and compile them with a JSON Schema 2020-12 validator. — DoD: the schemas embed via `go:embed`; a unit test compiles them and checks that the sha256 matches `PROVENANCE`; a CI step compares against the upstream digest.
- [ ] 2. Add the additive `bridgeSchema` with tables `bridge_commands`, `bridge_command_transitions`, `bridge_signal_outbox` and `bridge_write_permits`, plus their CHECKs and unique indexes. Apply it at start in the same way as `commerceSchema` (`internal/commerce/store.go`). (depends on 1) — DoD: applying the schema twice is a no-op; an integration test against Postgres passes.
- [ ] 3. Add `internal/bridge/store.go`: `Enqueue` (caller transaction, idempotent on `operation_key`), `Claim` (`SKIP LOCKED`, lease epoch and nonce rotation, lazy expiry), `SubmitResult` (ordered checks, CAS, signal-outbox insert, digest replay), `Cancel`, `ReadOutcome`, with typed errors. (depends on 2) — DoD: unit and integration tests cover every typed error with zero row change on refusal.
- [ ] 4. Add a `WriteFence` interface with a default `refusingFence`, and `IssueWritePermit`. The permit locks the command and the `aar_` row in one transaction, checks that it is human-approved, unexpired, unrevoked and has an equal `IntentHash` (`internal/workitems/action_approvals.go`), checks the current lease, then inserts the permit with unique `operation_key`. (depends on 3) — DoD: with the default fence, every permit is refused with `write_fence_unavailable`; with a test fence, the permit succeeds exactly once.
- [ ] 5. Add the bridge-provider principal in `internal/auth/bridge_provider.go`: `service:bridge-provider:<ref>`, `PermissionBridgeProvider`, the `MCTL_BRIDGE_PROVIDERS` parser (OIDC issuer/subject/audience; static token for tests only), and the `Identity()` case in `principal.go`. — DoD: parser tests cover malformed config, a wrong audience and a wrong subject.
- [ ] 6. Add router wiring in `internal/api/router.go`: the `MCTL_BRIDGE_ENABLED` gate (404 when disabled), the `requireBridgeProvider` middleware on `/api/v1/bridge/*`, the `denyBridgeProviderElsewhere` guard on all other routes, and a per-provider rate limiter. Wire env vars in `cmd/api/main.go` with defaults off. (depends on 3, 5) — DoD: route tests show 404 when disabled and 403 for every non-bridge principal kind.
- [ ] 7. Add `internal/api/handlers_bridge.go` with claim, result and write-permit handlers. They do schema validation, use `writeError`/`writeJSON`, write redacted audit entries and emit OTel spans. (depends on 4, 6) — DoD: handler tests assert the response codes, and that audit params contain no nonce, lease id, payload or token.
- [ ] 8. Add a `BridgeSignaler` interface plus `temporalclient.Client.SignalBridgeResult`, and a dispatcher loop over `bridge_signal_outbox` that signals only the stored `workflow_id`/`run_id`, with backoff and terminal `unknown` on not-found. Start it only when the feature is enabled and a Temporal client exists. (depends on 3) — DoD: a fake signaler test proves a retry after a transient error and exactly one delivery per `command_id`.
- [ ] 9. Docs: `docs/bridge.md` (contract, states, error codes, deployment gates: mctl-gitops#2456/#2469, P1 approval, no credentials issued), plus a CHANGELOG entry. — DoD: the doc lists every route, state and error code used in code.

## Tests

- [ ] T1. Contract: command and result fixtures shared with mctl-agents#1043, #1044, mctl-telegram#1236 and mctl-api#957 validate against the vendored schemas. Mutated fixtures (extra endpoint URL, token, tenant field, workflow id) are rejected.
- [ ] T2. Tenancy matrix: two team tenants, two owners in one tenant, revoked membership, unselected tenant, wrong audience, wrong lease and wrong receipt each fail closed. Each case asserts an identical row snapshot before and after, and no signal-outbox or permit row.
- [ ] T3. Claim/reclaim: a lease expires and the command is reclaimed under epoch+1. A result under the old epoch is refused with `lease_stale`, and the new holder succeeds.
- [ ] T4. Ambiguous callback: the same result is submitted twice and the second returns `replayed: true` with one signal. A different digest after completion returns `result_conflict`.
- [ ] T5. Cancel after claim: the result is refused with `command_cancelled` and no permit is issued.
- [ ] T6. Revoke after sign, before write: the `aar_` is revoked between claim and permit, so the permit is refused and only a `not_performed` completion is accepted. A concurrent revoke and permit race (two goroutines) yields either a refusal or a permit issued before the revoke commits, never both.
- [ ] T7. Crash after receipt: the result is committed and the dispatcher is killed before the signal. On restart the signal is delivered exactly once, and a read-back shows `completed` with no second effect.
- [ ] T8. At most one effect: two permits for the same `operation_key` (retry after timeout) produce one permit row. A retry reads the stored outcome, and an unknown effect stays `unknown`.
- [ ] T9. Privilege denial: a bridge-provider principal is refused on `/api/v1/agents/dev-loop/*`, `/work-items/*`, operations and MCP, and the fake `DevLoopClient` records zero calls. Runtime Temporal denial is recorded as gated on mctl-gitops#2456/#2469.
- [ ] T10. Disabled by default: with no env set, all bridge routes return 404 and the dispatcher does not start.
- [ ] T11. `go fmt`, `go vet`, `golangci-lint`, `go test ./...` pass. The MCP tool count in `server_test.go` is unchanged.

## Rollback

The feature ships disabled (`MCTL_BRIDGE_ENABLED` unset) and no provider credentials are issued, so rolling back means reverting the PR. The additive tables can stay in place harmlessly, or be dropped manually (`DROP TABLE bridge_write_permits, bridge_signal_outbox, bridge_command_transitions, bridge_commands`) once there is confirmation that no rows exist. If the feature has been enabled in a non-production environment:

1. Unset `MCTL_BRIDGE_ENABLED`. Routes return 404 immediately and the dispatcher stops.
2. Remove the `MCTL_BRIDGE_PROVIDERS` entries so provider tokens stop authenticating.
3. Mark pending or leased commands `cancelled` with a CAS update. Nothing in the bridge can authorize a real-world effect, because the provider is fake-only and the write fence refuses by default.
