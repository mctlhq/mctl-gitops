# Design: issue-1236-feat-glovo-m1d-separate-private-fake-pro

## Current state

- `test/glovo-poc/` is a nested Go module
  (`github.com/mctlhq/mctl-telegram/test/glovo-poc`, `go.temporal.io/sdk
  v1.50.0`). It contains:
  - `workflows/workflow.go`: `GlovoOrderWorkflow(ctx, Snapshot)` with signals
    `consent`, `handoff_opened`, `install_revoked`, `cancel`, query `status`,
    read activities retried (5 attempts), write activities `MaximumAttempts: 1`,
    disconnected-context purge on terminal paths, `OutcomeUnknown`.
  - `workflows/activities.go`: `Snapshot` (OrderID, TenantID, OwnerPrincipal,
    InstallID, InstallRevision, ConnectionRef, RequestRef, TTLs);
    `Activities{CP, Vault, Breaker, Log, AfterProviderWrite}`;
    `MutateBasket` verifies an ambiguous timeout by `ReadBasket` fingerprint and
    never re-sends; `PurgeOrder` / `PurgeConnection`; in-memory `Vault`.
  - `controlplane/controlplane.go`: in-memory `CP` with `Resolve`,
    `Revalidate`, `Authorize`, `DecodeRequest` (rejects `namespace`,
    `workflow_id`, `run_id`, `task_queue` - T16), handoff token issue/open/
    expire, deterministic `WorkflowID` and `Fire` dedupe (T10).
  - `fakeglovo/fakeglovo.go`: httptest synthetic provider; `NewClient` refuses
    non-loopback base URLs (`ErrNonLoopback`); `Fingerprint`, `Sanitize`,
    `Validate`, `RepeatWithout`.
  - `fairness/fairness.go`: `Breaker` and per-tenant `Limiter` (T18).
  - `leakcheck/leakcheck.go`: canary `Recorder`/`Find` used by T17.
  - Tests: T1-T3 (fakeglovo), T4-T9c, T11-T13, T17 (workflows), T10, T14-T16
    and handoff rules (controlplane), T18 (fairness).
- `.github/workflows/build.yml` job `test` already runs `go vet` and
  `go test -race -count=1 ./...` with `working-directory: test/glovo-poc`
  (nested modules are skipped by the root `go test ./...`). A separate job
  `docker-agent-worker` builds `Dockerfile.agent-worker` with `push: false`
  and its own GHA cache scope, kept separate so the required `docker` check
  name is not renamed.
- `Dockerfile.agent-worker` is the precedent for a second image from this repo:
  digest-pinned builder `golang:1.26.10-alpine@sha256:9ce2...`, `CGO_ENABLED=0`,
  `-X main.version=${APP_VERSION}`, OCI labels, non-root uid 1000, `tini`.
- `cmd/agent-worker/health_server.go` is the precedent for worker probes:
  `/livez`, `/healthz` alias, `/readyz`, `/metrics` via
  `internal/metrics.Registry`.
- `internal/audit/redact.go` (`NewRedactingHandler`, `sensitiveKeys`) and
  `internal/netsafe` (`Client`, `PublicAddr`) exist in the root module.
- The root `go.mod` has no Temporal dependency (`grep -c temporal go.mod` = 0).
- `docs/adr/0009-assistant-temporal-tenancy.md` (queue `assistants-provider-glovo`,
  provider worker in its own K8s namespace, no Vault token, no DevLoop access)
  and `docs/adr/0010-glovo-multitenant-connections.md` (provider namespace
  `mctl-assistants-provider-glovo`, `aar_` receipt fence, typed refusal codes,
  gates G0-G6, test catalog T0-T16) define the target boundary. Both are
  "Proposed"; nothing is deployed.
- `docs/glovo_contract_test.go` enforces the facade tool allowlist and the
  forbidden property set (`tenant`, `namespace`, `task_queue`, `workflow_id`,
  `url`, `endpoint`, `cookie`, `session`, `token`, ...).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: public server,
  image `ghcr.io/mctlhq/mctl-telegram` tag `0.135.0`, tenant `labs`.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`: second
  image `ghcr.io/mctlhq/agent-worker-preview`, `ingress.enabled: false`, tag
  auto-bumped by `preview-deploy.yml`.
- `grep -rli "glovo|assistants"` over `$MCTL_GITOPS_ROOT/services` and
  `$MCTL_GITOPS_ROOT/tenants`: no matches. No Glovo provider service or
  tenant exists in this gitops checkout. Tenants present: admins,
  commerce-proof, erpact, karabu, labs, mctl, namax66.
- Temporal namespace/RBAC state (`infra-components/data/temporal/...`) is not
  inside the mounted `platform-gitops/services` / `tenants` paths and was not
  observed; the ADRs' description of it is taken as-is (see Open questions).
- mctl MCP tools were not called; the gitops checkout was sufficient for the
  "no existing deployment" fact, and this slice changes no deployment.

## Proposed solution

### 1. New nested module `provider/glovo/`

Module path `github.com/mctlhq/mctl-telegram/provider/glovo`, Go 1.26, its own
`go.mod`/`go.sum` pinned to the same `go.temporal.io/sdk v1.50.0` /
`go.temporal.io/api v1.63.5` as the PoC. Keeping it a separate module keeps
Temporal and provider code out of the root module and out of the public
`cmd/server` binary, mirrors the PoC's isolation, and makes the import boundary
mechanical. It does not import the root module (no `internal/...` reuse);
the small redaction and probe helpers it needs are re-implemented locally
with tests so the worker's dependency closure stays minimal and reviewable.

Layout:

```
provider/glovo/
  go.mod
  cmd/glovo-provider-worker/main.go      config, gates, worker, probes, signals
  internal/fakeonly/                     build-tag + runtime FAKE_ONLY gate, env deny-scan
    gate_fake.go       //go:build !glovo_real   const RealAdapterCompiled = false
    gate_real.go       //go:build glovo_real    compile error stub (no real adapter in M1)
  internal/protocol/v1alpha1/            versioned control-to-provider request/response types,
                                         strict JSON decode (DisallowUnknownFields + forbidden keys)
  internal/bridge/                       ControlBridge interface + fail-closed wrapper;
    fake/                                deterministic in-memory bridge for tests (no prod impl)
  internal/fakestore/                    promoted fakeglovo: deterministic fixture menu/basket,
                                         in-process, loopback-only, Fingerprint/Sanitize/Validate
  internal/basket/                       idempotency ledger keyed (tenant, order, intent_hash),
                                         apply/read-back/compare
  internal/activities/                   ResolveScope, QuoteOrder, MutateBasket, ReadBasket,
                                         IssueHandoff, ExpireHandoff, PurgeOrder, PurgeConnection
  internal/workflows/                    promoted GlovoOrderWorkflow (provider-side)
  internal/fairness/                     promoted Breaker + per-tenant Limiter
  internal/obs/                          slog redacting handler, metrics, tracer, audit events
  internal/health/                       /livez /healthz /readyz /metrics server
  internal/leakcheck/                    promoted canary scanner (test helper)
```

### 2. Fake-only enforcement (code and config)

- Build time: the only adapter is `fakestore`. `gate_real.go` under
  `//go:build glovo_real` contains a deliberate compile failure in M1, so a
  real-adapter build is impossible without a reviewed code change. A test
  asserts `RealAdapterCompiled == false` in the default build.
- Runtime: `main` calls `fakeonly.Check(os.Environ())` first. It requires
  `FAKE_ONLY=true` exactly, and refuses to start if any env var name matches
  the Glovo credential/session deny patterns (names only are logged).
- `fakestore` runs in-process; its client keeps the PoC `ErrNonLoopback`
  rule, so no non-loopback provider URL can be constructed. No default
  endpoint or credential exists anywhere in code or Dockerfile `ENV`.

### 3. Temporal identity confinement

- Config: `TEMPORAL_HOSTPORT`, `TEMPORAL_NAMESPACE`, `TEMPORAL_TASK_QUEUE`,
  optional TLS cert/key/CA file paths. `TEMPORAL_NAMESPACE` must equal the
  compiled constant `mctl-assistants-provider-glovo` and the queue must equal
  `assistants-provider-glovo`; anything else (including `mctl-assistants`,
  `mctl-agents`, `kuptsi`) is a startup error.
- The worker creates one `client.Client` used only by `worker.New`. No code
  path calls `SignalWorkflow`, `ListWorkflow`, `TerminateWorkflow`,
  `CancelWorkflow`, `QueryWorkflow` or `ExecuteWorkflow`; an AST/import test
  (`go/parser` over `provider/glovo/...`) fails if any of those selectors
  appears outside `_test.go`.
- Real namespace-level RBAC (provider identity denied control/DevLoop) is a
  platform property (mctl-gitops#2469, gate G5); the negative test here
  proves the code never attempts it and that misconfiguration toward those
  namespaces refuses to start. A test against a Temporal dev server with
  authorizer is listed as blocked until #2469.

### 4. Versioned protocol and fenced mutation boundary

- `protocol/v1alpha1.ProviderRequest{Version, ExecutionRef (we_), TenantRef,
  OwnerRef, ConnectionRef (gcn_), InstallRef, InstallRevision, OrderRef,
  IntentHash, ApprovalRef (aar_)}`; decode uses `DisallowUnknownFields` and the
  PoC T16 forbidden-key list extended with `role`, `url`, `endpoint`, `cookie`,
  `session`, `token`, `password`. Prefix/format validation on every ref.
- `bridge.ControlBridge`:
  `ResolveScope(ctx, req) (Scope, error)` and
  `ConsumeApproval(ctx, req, basketFingerprint) error`. The `failClosed`
  wrapper maps timeouts, transport errors, and malformed answers to a
  non-retryable `ApplicationError` of type `bridge_unavailable`.
  Only `bridge/fake` exists in this slice; `main` refuses to start with a
  non-fake bridge configured because none is compiled in (production wiring
  blocked on mctl-agents#1043 / mctl-api#953/#954).
- `activities.MutateBasket` order of operations:
  1. strict decode + ref validation;
  2. kill switch / breaker / per-tenant limiter;
  3. `ResolveScope` (live tenant, owner, install revision, connection state);
     refusal codes from ADR 0010: `not_authorized`, `not_found` (foreign
     order), `stale_install`, `connection_revoked`, `connection_expired`;
  4. idempotency ledger lookup for `(tenant, order, intent_hash)`: if an
     effect is already recorded, read back the basket and return its
     fingerprint without re-applying;
  5. read back the current fake basket; if fingerprint already equals the
     intended one, record and return (covers ambiguous timeout of a prior
     attempt);
  6. `ConsumeApproval` (single use; wrong `aar_`, wrong `we_`, intent hash
     mismatch, expired or replayed receipt refuse);
  7. apply to `fakestore`; on ambiguous timeout read back and compare,
     otherwise `write_unverified` -> workflow `OUTCOME_UNKNOWN`;
  8. record in ledger, emit audit event (opaque ids + outcome only).
  Writes keep `MaximumAttempts: 1` as in the PoC; steps 4-5 make any
  operator-driven or Temporal retry safe.
- `IssueHandoff` and the `handoff_opened` path call `ResolveScope` again
  (handoff revalidation); revocation/cancel signals are handled as in the PoC
  `pending()` logic with revoke winning over cancel, and purge in a
  disconnected context.

### 5. Operations

- `health`: `/livez`, `/healthz` (alias), `/readyz` (poller started, kill
  switch off, breaker closed), `/metrics` (Prometheus registry local to the
  module; names prefixed `mctl_glovo_provider_`). Listens on
  `HEALTH_ADDR` default `:8081`; no public ingress is defined anywhere.
- Kill switch: `GLOVO_PROVIDER_DISABLED=true` refuses new mutations with
  `provider_disabled`; breaker open does the same.
- Shutdown: `signal.NotifyContext(SIGTERM, SIGINT)` -> `worker.Stop()` with
  `WorkerStopTimeout` (default 25s, below a 30s pod grace), health server
  `Shutdown`, exit 0.
- Observability: slog JSON with a local redacting handler (keys from
  `internal/audit/redact.go` semantics plus `basket`, `item`, `receipt`,
  `approval`, `address`); OpenTelemetry tracer via Temporal interceptor with
  attributes limited to opaque refs; audit events typed (`scope_refused`,
  `mutation_applied`, `mutation_deduped`, `handoff_issued`, `purged`).
- `Dockerfile.glovo-provider-worker`: builder same pinned
  `golang:1.26.10-alpine@sha256:...`, `WORKDIR /src/provider/glovo`, copy only
  `provider/glovo`, `go build -trimpath -ldflags="-s -w -buildid= -X
  main.version=${APP_VERSION}"`; runtime `gcr.io/distroless/static-debian12:nonroot`
  pinned by digest (no shell, no package manager), `USER 1000:1000`
  (repo convention for non-root user 1000), `ENV FAKE_ONLY=true`,
  `EXPOSE 8081`, OCI labels with title
  `mctl-telegram-glovo-provider-worker`. A documented pod spec fragment
  (`docs/runbooks/glovo-provider-worker.md`) states the required security
  context (`runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation:
  false`, drop ALL, seccomp RuntimeDefault), resource requests/limits
  (100m/64Mi request, 500m/256Mi limit), default-deny egress except
  Temporal frontend, and rollback by re-pinning the previous image digest.
  This is documentation only; no GitOps file is created.
- CI (`.github/workflows/build.yml`): add vet + `go test -race -count=1 ./...`
  steps for `provider/glovo` inside the existing required `test` job (same
  reasoning as the PoC steps), and a new job `docker-glovo-provider-worker`
  with `push: false`, `load: true`, cache scope `glovo-provider-worker`, and an
  assertion step that runs the image with `FAKE_ONLY` unset (must exit
  non-zero) and with a `GLOVO_SESSION_TOKEN` set (must exit non-zero), and
  inspects `docker image inspect` for `User` non-root. No push, no GHCR
  login, no release workflow change.
- `.dockerignore` already excludes only VCS/editor/local dirs; the new
  Dockerfile copies only `provider/glovo`, so the public image is unaffected.

### 6. Reuse map from the PoC

| PoC | Promoted to | Change |
| --- | --- | --- |
| `fakeglovo` (T1-T3) | `internal/fakestore` | in-process only, deterministic fixtures, no httptest dependency at runtime |
| `workflows` (T4-T9c, T11-T13, T17) | `internal/workflows`, `internal/activities` | `CP`/`Vault` replaced by `ControlBridge` + ledger; snapshot uses protocol refs |
| `controlplane.DecodeRequest` (T16) | `internal/protocol/v1alpha1` | extended forbidden keys, versioned |
| `controlplane` T10, T14, T15 | `bridge/fake` semantics + tests | control-plane state stays mctl-api's; only fake here |
| `fairness` (T18) | `internal/fairness` | unchanged logic, metrics added |
| `leakcheck` (T17) | `internal/leakcheck` | unchanged |

`controlplane.CP` itself (links, membership, handoff token minting, `Fire`)
is control-plane responsibility (mctl-api / `mctl-assistants`) and is NOT
promoted into the provider worker; only its refusal semantics are mirrored in
`bridge/fake` for tests.

## Alternatives

1. **Add packages to the root module (`internal/glovoprovider`, `cmd/glovo-provider-worker`).**
   Simpler build, can reuse `internal/audit` and `internal/metrics`. Dropped:
   pulls the Temporal SDK into the public server's module graph and makes it
   easy for `cmd/server` or `internal/mcp` to import provider code; the
   isolation the issue demands would rest on convention instead of module
   boundaries.
2. **Build the worker directly from `test/glovo-poc`.** Fastest, but the PoC
   is test-shaped (in-memory CP owning tenancy, httptest server, test seams
   like `AfterProviderWrite`) and the issue explicitly asks to promote only
   reviewed, reusable logic. Shipping test code as a release artifact also
   blurs what was reviewed.
3. **Run the provider inside the public `tg.mctl.ai` process or a queue in
   `mctl-agents`.** Rejected by the issue and ADR 0009 (Option A): no queue
   RBAC, mixes untrusted provider I/O with privileged DevLoop queues.

## Platform impact

- Migrations: none. No DB schema, no root-module dependency change.
- Backward compatibility: public image (`Dockerfile`), agent-worker image and
  required check names (`test`, `docker`) unchanged; new CI steps run in the
  existing `test` job and a new non-required job.
- Resources: CI time increases (one more module race-tested, one more image
  build with its own cache scope). No runtime resources consumed: nothing is
  deployed.
- Risks and mitigations:
  - Real adapter sneaks in later -> compile-failing `glovo_real` stub, runtime
    `FAKE_ONLY` gate, env deny-scan, CI negative image runs.
  - Worker pointed at control/DevLoop namespace -> compiled-constant namespace
    and queue check; AST test forbids client calls beyond the worker poller.
    Actual Temporal RBAC remains an external gate (G5, mctl-gitops#2469).
  - Bridge contract drift when mctl-agents#1043 lands -> protocol is
    explicitly `v1alpha1`, isolated in one package; fail-closed wrapper means
    an incompatible peer refuses rather than allows.
  - PII in logs/history -> redacting handler, opaque-only payloads, canary
    converter and leak-scan tests promoted from T17.
  - Duplicate code with the PoC -> accepted for this slice; PoC remains the
    reviewed reference, convergence is an open question.
