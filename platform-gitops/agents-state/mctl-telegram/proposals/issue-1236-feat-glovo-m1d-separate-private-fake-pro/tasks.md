# Tasks: issue-1236-feat-glovo-m1d-separate-private-fake-pro

- [ ] 1. Create nested module `provider/glovo` (`go.mod` with `go.temporal.io/sdk v1.50.0`, `go.temporal.io/api v1.63.5`, Go 1.26) and skeleton `cmd/glovo-provider-worker/main.go` printing version — DoD: `cd provider/glovo && go build ./... && go vet ./...` passes; root `go.mod` unchanged (no temporal dependency).
- [ ] 2. `internal/fakeonly`: `gate_fake.go` (`//go:build !glovo_real`, `RealAdapterCompiled=false`), `gate_real.go` (`//go:build glovo_real`, deliberate compile error), `Check(env []string) error` requiring `FAKE_ONLY=true` and refusing Glovo credential/session env names (depends on 1) — DoD: unit tests for missing/false/other values and each deny pattern; error messages contain names only.
- [ ] 3. `internal/protocol/v1alpha1`: `ProviderRequest`/`ProviderResult`, strict decoder (`DisallowUnknownFields`, forbidden keys from PoC T16 plus `role`, `url`, `endpoint`, `cookie`, `session`, `token`, `password`), ref prefix validation (`we_`, `gcn_`, `aar_`) (depends on 1) — DoD: table tests for each forbidden key and malformed ref.
- [ ] 4. `internal/fakestore`: promote `test/glovo-poc/fakeglovo` (fixture menu, basket, `Fingerprint`, `Sanitize`, `Validate`, `RepeatWithout`, loopback-only client rule) as deterministic in-process store with injectable timeout fault (depends on 1) — DoD: PoC T1-T3 and `TestClientRefusesNonLoopback`, `TestSessionsAreIsolated` ported and green.
- [ ] 5. `internal/bridge`: `ControlBridge` interface (`ResolveScope`, `ConsumeApproval`), `failClosed` wrapper mapping timeout/transport/malformed to non-retryable `bridge_unavailable`; `bridge/fake` deterministic implementation with tenants, principals, installs/revisions, connections, single-use receipts bound per ADR 0010 (depends on 3) — DoD: no non-fake implementation exists; `main` cannot select another.
- [ ] 6. `internal/basket`: idempotency ledger keyed `(tenant, order, intent_hash)` with apply/read-back/compare (depends on 4) — DoD: concurrent apply under `-race` yields one effect.
- [ ] 7. `internal/fairness` (promote PoC Breaker + Limiter) and `internal/obs` (redacting slog handler, metrics `mctl_glovo_provider_*`, tracer interceptor with opaque attributes, typed audit events) (depends on 1) — DoD: T18 ported; redaction tests for `receipt`, `approval`, `basket`, `item`, `address`, `token`, `session`.
- [ ] 8. `internal/activities` and `internal/workflows`: promote `GlovoOrderWorkflow` and activities, replacing `controlplane.CP`/`Vault` with `ControlBridge` + ledger; implement the 8-step `MutateBasket` sequence from design.md section 4; revalidate on `IssueHandoff` and handoff open; revoke-wins-over-cancel terminal handling with disconnected purge (depends on 4, 5, 6, 7) — DoD: PoC T4-T9c, T11-T13, T17 ported and green.
- [ ] 9. Temporal confinement in `main`: compiled constants `mctl-assistants-provider-glovo` / `assistants-provider-glovo`, refuse other values, single client used only by `worker.New`, optional TLS file config, no real bridge (depends on 2, 8) — DoD: startup tests for wrong namespace/queue; AST test over non-test files forbids `SignalWorkflow`, `ListWorkflow`, `TerminateWorkflow`, `CancelWorkflow`, `QueryWorkflow`, `ExecuteWorkflow`, `SignalWithStartWorkflow`.
- [ ] 10. `internal/health` + kill switch + graceful shutdown: `/livez`, `/healthz`, `/readyz`, `/metrics` on `HEALTH_ADDR` (default `:8081`); `GLOVO_PROVIDER_DISABLED`; `signal.NotifyContext` with bounded `WorkerStopTimeout` (depends on 9) — DoD: readiness transitions tested; SIGTERM test exits 0 with in-flight activity completed or cancelled deterministically.
- [ ] 11. `Dockerfile.glovo-provider-worker`: digest-pinned builder `golang:1.26.10-alpine`, copy only `provider/glovo`, `-trimpath -buildid=`, digest-pinned distroless static runtime, non-root uid 1000, `ENV FAKE_ONLY=true`, `EXPOSE 8081`, OCI labels (`mctl-telegram-glovo-provider-worker`) (depends on 10) — DoD: two consecutive builds of the same commit produce identical binary sha256.
- [ ] 12. CI in `.github/workflows/build.yml`: vet + `go test -race -count=1 ./...` for `provider/glovo` in the existing `test` job; new job `docker-glovo-provider-worker` (`push: false`, `load: true`, cache scope `glovo-provider-worker`) with assertions: image user non-root, exits non-zero without `FAKE_ONLY`, exits non-zero with `GLOVO_SESSION_TOKEN` set (depends on 11) — DoD: CI green on the PR; no registry login or push step anywhere in the job.
- [ ] 13. Docs: `docs/runbooks/glovo-provider-worker.md` (config, probes, kill switch, required pod security context, resource limits 100m/64Mi req and 500m/256Mi limit, default-deny egress, rollback by re-pinning previous digest, gates G2/G3/G5 still blocking deploy) and a reuse map from PoC T1-T18 (depends on 12) — DoD: doc states explicitly that no GitOps, Vault, DNS, namespace or deploy change is authorized by this code.

## Tests

- [ ] T1. Ported PoC T1-T3: search/menu sanitized, repeat-without-category, modifiers (fakestore).
- [ ] T2. Ported PoC T4-T9c, T11-T13: collision, fee change, stale install, expiry, revoke mid-wait / after handoff / during write, retry discipline, duplicate consent, outcome unknown.
- [ ] T3. Ported PoC T10/T14/T15/T16 semantics against `bridge/fake` and `protocol/v1alpha1`.
- [ ] T4. Two tenants: tenant B's refs against tenant A's order -> `not_authorized`/`not_found`, zero fakestore writes (write counter == 0).
- [ ] T5. Same tenant, distinct principals: principal B cannot mutate principal A's basket or reuse A's `gcn_`; zero writes.
- [ ] T6. Foreign order id, stale install revision, revoked connection, expired connection: each typed refusal, zero writes.
- [ ] T7. Wrong `aar_`, wrong `we_`, mismatched intent hash, expired receipt, replayed receipt: each refused, zero writes; receipt consumed at most once.
- [ ] T8. Exactly-once: activity retried after success, after ambiguous timeout with effect applied, after ambiguous timeout without effect; observable basket effect count == 1 (or 0 with `OUTCOME_UNKNOWN`), never 2.
- [ ] T9. Cancellation/revocation after each activity boundary (quote, consume, apply, read-back, issue handoff) and at handoff open with revalidation: deterministic terminal state table.
- [ ] T10. Bridge failure: timeout, connection error, malformed answer, partial answer -> `bridge_unavailable`, zero writes.
- [ ] T11. Secret/PII leak regression: canary in tenant, basket and receipt values never appears in history payloads (canary converter), logs, metrics labels or results.
- [ ] T12. Fake-only: default build has `RealAdapterCompiled == false`; `go build -tags glovo_real` fails; runtime refuses without `FAKE_ONLY=true` and with any Glovo credential env name.
- [ ] T13. Temporal confinement: startup refuses `mctl-assistants`, `mctl-agents`, `kuptsi` and other queues; AST test finds no client control calls.
- [ ] T14. Health/readiness/kill switch/breaker transitions; graceful SIGTERM shutdown.
- [ ] T15. Import boundary: `go list -deps ./cmd/server` in the root module contains no `provider/glovo` or `go.temporal.io` package.
- [ ] T16. All of the above run under `go test -race -count=1 ./...` in `provider/glovo`; CI image assertions in `docker-glovo-provider-worker`.

## Rollback

The change is additive: a new nested module, a new Dockerfile, new CI steps and
a new non-required CI job, plus docs. Nothing is published or deployed. To roll
back, revert the merge commit (`git revert -m 1 <merge>`), which removes
`provider/glovo/`, `Dockerfile.glovo-provider-worker`, the CI additions and the
runbook; the public server image, agent-worker image and `test/glovo-poc` are
untouched. For any future deployment (separately approved), rollback is
re-pinning the previous image digest in GitOps or setting
`GLOVO_PROVIDER_DISABLED=true`.
