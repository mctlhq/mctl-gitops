# Design: issue-1262-feat-glovo-re-platform-fake-provider-wor

## Current state

`main` (HEAD `27c671d`, the merge of #1259) has **no `provider/glovo/` module**. What `main` does have:

- `internal/glovo/` (authn, config, contract, facade, mctlapi, tools) and `cmd/glovo-mcp`, the
  OAuth MCP facade. It is unrelated to the provider worker and stays untouched.
- `internal/glovo/imports_test.go`. Its `TestFacadeBinaryImportBoundary` uses `go list -deps` to
  forbid `go.temporal.io/` and Telegram packages in `cmd/glovo-mcp`. That is the pattern the new
  provider boundary test follows.
- The root `go.mod` has no Temporal requirement and there is no `go.work`. `.github/workflows/build.yml`
  vets and tests the nested module `test/glovo-poc` (lines 84-89) and builds `docker-glovo-mcp`.
  There are no provider-worker steps.

The provider module exists only on the draft #1258 branch
`feat/agents-issue-1236-feat-glovo-m1d-separate-private-fake-pro` (head `1f1dbc19`; the shallow clone
shares no history with `main`). On that branch:

- `provider/glovo/go.mod` requires `go.temporal.io/sdk v1.50.0` and `prometheus/client_golang`.
- `cmd/glovo-provider-worker/main.go` dials Temporal, registers `workflows.GlovoOrderWorkflow` and
  `*activities.Activities`, and wires `bridge.FailClosed(bridgefake.New(...))`.
  `config.go` hard-codes namespace `mctl-assistants-provider-glovo` and queue
  `assistants-provider-glovo`, and reads `TEMPORAL_HOSTPORT` / `TEMPORAL_TLS_*`,
  `GLOVO_PROVIDER_DISABLED`, `WORKER_STOP_TIMEOUT` and `HEALTH_ADDR`.
- `internal/bridge/bridge.go` defines `ControlBridge{ResolveScope, ConsumeApproval}`, the refusal
  codes (`not_authorized`, `approval_invalid`, `write_unverified`, `tenant_busy`, ...) and `FailClosed`.
- `internal/activities/activities.go` (imports `go.temporal.io/sdk/temporal`) implements
  `QuoteOrder`, `MutateBasket`, `ReadBasket`, `IssueHandoff` and others over `fakestore`,
  `basket.Ledger`, `fairness.Limiter`/`Breaker` and the kill switch.
- `internal/workflows/` holds the Temporal workflow and its testsuite harness. `internal/obs/obs.go`
  imports `go.temporal.io/sdk/activity` and `interceptor` for a metrics interceptor;
  `internal/obs/redact.go` is a redacting slog handler.
- `internal/protocol/v1alpha1/protocol.go` defines a home-grown `ProviderRequest`
  (`execution_ref`, `tenant_ref`, `install_revision`, `intent_hash` as 64 hex digits, ...). This is not
  the bridge wire.
- `internal/fakestore/fakestore.go` is an in-process synthetic store. It has menu items `m1`-`m3`,
  sessions keyed by `tenant|connection`, `MutateBasket` with fault knobs (`SetWriteTimeoutOnce`,
  `SetWriteLostOnce`, `SetAlways429`, `SetTransientReads`) and "deliberately no PlaceOrder or Pay".
- `internal/fakeonly` holds a build tag (`gate_fake.go`/`gate_real.go`) and `Check(env)`, which
  requires `FAKE_ONLY=true` and refuses env names matching `GLOVO_*TOKEN*`, `GLOVO_*SESSION*`,
  `GLOVO_*COOKIE*`, `GLOVO_*PASSWORD*`, `GLOVO_API_*` and `GLOVO_BASE_URL`.
  `internal/leakcheck` holds canary strings and a `Recorder`. `internal/health` serves probes and
  metrics on `:8081`.
- `Dockerfile.glovo-provider-worker` builds only `provider/glovo/` into
  `distroless/static-debian12:nonroot` with `USER 1000:1000` and `ENV FAKE_ONLY=true`. The
  `build.yml` job `docker-glovo-provider-worker` checks non-root and two negative runs (no
  `FAKE_ONLY`; `GLOVO_SESSION_TOKEN` set). `docs/runbooks/glovo-provider-worker.md` documents
  "default-deny egress except the Temporal frontend".

The mctl-api bridge (read from mctlhq/mctl-api `main` at `a9ca581`):

- `docs/bridge.md` defines three POST routes, all returning 404 while disabled. `claim` takes an
  optional `{"max": n}` and returns `{"schema_version","commands":[...]}`
  (`internal/api/handlers_bridge.go: BridgeClaim`); `MaxClaimBatch=10` and `DefaultLeaseTTL=60s`
  (`internal/bridge/store.go`). `write-permit` takes `{"lease_token"}` and returns
  `{"command_id","fence_ref","issued_at"}`. `result` returns
  `{"command_id","status","effect_state","result_digest","replayed"}`.
- Errors are `{"error","code"}` (`writeErrorCode`), mapped in `bridgeStatus`: 400 `invalid_document`
  / `invalid_input`; 404 `command_not_found` (also a foreign tenant or provider); 409 `lease_stale`,
  `binding_mismatch`, `command_cancelled`, `command_expired`, `result_conflict`,
  `already_completed`, `not_mutating`, `permit_already_issued`; 422 `result_inconsistent`; 403
  `write_fence_refused`; 503 `write_fence_unavailable` / `bridge_unavailable`; 500 `bridge_internal`.
- `SubmitResult` requires `worker_identity == "provider:"+ProviderRef`, an `execution_id` and
  `attempt` matching the row, and a live lease. `approval_refused` requires `provider_effect=none`;
  `applied` requires an issued permit (`EffectPermitted`).
- `internal/bridge/schema/` holds `command.schema.json` (sha256 `b857f62b...6dae1`),
  `result.schema.json` (sha256 `c91bb86e...354f`), `PROVENANCE` and `testdata/` (6 fixtures). It is
  validated with `github.com/santhosh-tekuri/jsonschema/v6`, with `AssertFormat()`. Command kinds:
  `quote`, `place_order_fake`, `cancel_order_fake`, `read_status`. The payload has only
  `item_codes` (<=20), `quantity_total` and `note`. `approval_ref` is required for the two mutating
  kinds.

Deployed state checked:
- `mctl_list_services(team=labs)` (complete=true, 21 services): no Glovo provider or `glovo-mcp`
  service is deployed.
- `$MCTL_GITOPS_ROOT/services/labs/`: no `glovo*` directory. `grep -ril glovo` over
  `services/` and `tenants/` matched nothing.
- `grep -rl MCTL_BRIDGE` over `services/`: no match. The mctl-api deployment values were **not
  located** in the mounted checkout, so whether the bridge is enabled in production was not
  observed. That gap is recorded under Open questions; it is not a finding of "disabled".
  `docs/bridge.md` states the bridge ships dark.

## Proposed solution

A new PR from `main` adds `provider/glovo/`. It ports the retained packages from #1258 `1f1dbc19`
and replaces the Temporal and ControlBridge layers with a bridge client.

### Module layout

```
provider/glovo/
  go.mod                         # requires prometheus/client_golang, santhosh-tekuri/jsonschema/v6; no temporal
  cmd/glovo-provider-worker/
    main.go                      # gates -> config -> health -> poller.Run(ctx)
    config.go                    # env config (below)
    boundary_test.go             # module + root boundary tests
    main_test.go                 # startup gates, shutdown, TEMPORAL_* refusal
  internal/protocol/v1alpha1/    # wire (replaces ProviderRequest)
    schema/command.schema.json   # byte copies from mctl-api internal/bridge/schema
    schema/result.schema.json
    schema/PROVENANCE
    schema/testdata/*.json       # the 6 mctl-api golden fixtures, byte copies
    wire.go                      # Command, Result, Payload, ClaimResponse, ParseCommand, EncodeResult
    wire_test.go                 # sha256 pin + golden fixtures
  internal/bridgeclient/
    client.go                    # Claim, WritePermit, SubmitResult; typed *APIError{Status, Code}
    transport.go                 # origin-pinned RoundTripper, no proxy, no redirects, size limits
    credential.go                # file-backed bearer source
    poller.go                    # poll loop + per-command state machine
    bridgefake/bridgefake.go     # httptest fake bridge (tests only)
  internal/executor/executor.go  # command -> fakestore effect -> Result (replaces activities)
  internal/fakestore/            # ported; gains fake order effects keyed by command_id
  internal/fairness/ fakeonly/ health/ leakcheck/ obs/   # ported; obs loses temporal imports
```

The new module does not have `internal/workflows`, `internal/activities`, `internal/bridge`,
`internal/bridge/fake` or `internal/basket`. Keeping the package path `internal/protocol/v1alpha1`
limits churn; its contents are replaced.

### Wire (`internal/protocol/v1alpha1`)

- `//go:embed schema/*.json schema/PROVENANCE` and compile both schemas once with
  `jsonschema/v6`, `AssertFormat()`, under their `$id` URLs. This is the same library and settings as
  mctl-api `internal/bridge/schema.go`, so both sides accept exactly the same documents.
- `ParseCommand(raw json.RawMessage) (Command, error)`: validate against the command schema, then
  strict-decode (`DisallowUnknownFields`, no trailing data). On failure it returns `ErrInvalid` and a
  best-effort `Envelope{CommandID, ExecutionID, LeaseToken, Attempt}`. The envelope is filled only
  for fields that individually match their schema patterns, so the caller can decide whether a
  terminal result is possible.
- `Result` struct with exactly the 12 schema properties. `EncodeResult(Result) ([]byte, error)`
  marshals and then validates against `result.schema.json`, so an extra field or a bad enum can never
  leave the process.
- `wire_test.go` checks:
  - `sha256(schema/*.json)` equals the two pinned digests;
  - `PROVENANCE` names the same digests and merge `14645f93`;
  - the fixtures in `testdata` validate or fail exactly as their names say (`command.valid`,
    `result.valid` pass; `command.extra-field`, `command.bad-ref-pattern`,
    `command.mutation-missing-approval`, `result.extra-field` fail).

### Bridge client (`internal/bridgeclient`)

- Config:
  - `MCTL_API_BASE_URL`: required. It must be an origin only (scheme + host [+ port], no path, query,
    fragment or userinfo). The scheme is `https`; `http` is allowed only for loopback hosts, so
    `httptest` works.
  - `MCTL_BRIDGE_CREDENTIAL_FILE`: required path. This name deliberately avoids the `fakeonly`
    `GLOVO_*TOKEN*` deny pattern.
  - `BRIDGE_WORKER_IDENTITY`: default `provider:glovo`; must match `^provider:[a-z0-9-]{1,32}$`.
  - `BRIDGE_CLAIM_MAX`: default 4, range 1..10.
  - `BRIDGE_POLL_INTERVAL`: default 2s, range 500ms..60s.
  - The worker refuses to start if any `TEMPORAL_*` variable is set. That catches stale manifests;
    the error lists names only.
- Credential: `credential.go` reads the file on each request. That allows rotation without a restart.
  It trims whitespace, rejects an empty or >4 KiB file, and stores the value in a type whose
  `String`/`LogValue`/`MarshalJSON` return `[redacted]`. The value is set only as the
  `Authorization: Bearer` header. Errors name the setting `MCTL_BRIDGE_CREDENTIAL_FILE`, never the
  path contents.
- Transport: an `http.Transport` with `Proxy: nil`, plus a wrapping RoundTripper. The wrapper
  refuses (before dialing) any request whose scheme/host/port differs from the configured origin, and
  any path outside `/api/v1/bridge/commands/`. The client has `CheckRedirect` returning an error, a
  10s per-request timeout, and a 64 KiB response body cap. Only `Content-Type: application/json` is
  sent.
- Methods:
  - `Claim(ctx, max) ([]json.RawMessage, error)`;
  - `WritePermit(ctx, commandID, leaseToken) (Permit, error)`;
  - `SubmitResult(ctx, commandID, body []byte) (SubmitAck, error)`.
  A non-2xx response decodes `{"code"}` into `*APIError{Status, Code}` and never keeps the body. A
  claim response must have `schema_version == "bridge.mctl.ai/v1alpha1"`.
- Poller: on a claim error, back off exponentially with jitter (cap 60s). A claim 404 (bridge
  disabled) or 401/403 (`bridge_provider_required`/`bridge_provider_gate`) keeps the readiness probe
  failing and backs off at the cap. Each claimed command runs in its own goroutine, bounded by
  `fairness.Limiter` per `tenant_ref` and by the claim batch. Every command runs under a context
  ending at `min(expires_at, claim time + lease TTL 60s - 5s margin)`.

### Per-command state machine (`poller.go` + `internal/executor`)

1. Run `ParseCommand`.
   - If invalid and the envelope is complete, submit a terminal result
     (`failed_terminal`/`provider_rejected`/`none`, `error_detail="schema_invalid"`).
   - If invalid and the envelope is incomplete, drop the command and increment
     `mctl_glovo_provider_commands_dropped_total{reason="schema_invalid"}`.
   - If `audience != BRIDGE_WORKER_IDENTITY`, treat it the same as a schema failure, with
     `error_detail="audience_mismatch"`.
2. Pre-flight checks:
   - `cancel_requested=true`: submit `cancelled`/`none`/`error_code=none`.
   - Now past `expires_at`: stop, send nothing (the server sweeps to `expired`).
   - Kill switch set or circuit breaker open: submit `failed_retryable`/`provider_unavailable`/`none`.
3. Read-only kinds (`quote`, `read_status`) go straight to the executor and never request a permit.
   `quote` prices `payload.item_codes` and `quantity_total` against the fakestore catalogue.
   `read_status` reads the fake order of `order_ref`. Success is `succeeded`/`none`/`none`, with
   `result_ref` set to a deterministic `res_` id derived from `command_id`.
4. Mutating kinds (`place_order_fake`, `cancel_order_fake`):
   1. Read back `fakestore.EffectOf(command_id)`. If an effect is already confirmed, report
      `succeeded`/`applied`; there is no second permit and no second effect.
   2. Otherwise call `WritePermit`. Any error means no effect, mapped as in the table below.
   3. With a permit, call `fakestore.PlaceOrderFake` / `CancelOrderFake(sessionKey, commandID,
      orderRef, lines)`, then read back `EffectOf(command_id)`.
      - Confirmed: `succeeded`/`applied`.
      - Write error with read-back not confirming the effect: `failed_terminal`/`unknown`,
        `error_code=provider_unavailable`, increment
        `mctl_glovo_provider_ambiguous_writes_total`. The command is marked done locally and is
        never retried in-process.
      - Deterministic refusal before the write (item unavailable, no such order for cancel):
        `failed_terminal`/`provider_rejected`/`none`.
5. Encode the result (schema-validated) once and keep those bytes. `SubmitResult` follows the table
   below and retries only these bytes.

`internal/fakestore` gains `PlaceOrderFake`, `CancelOrderFake`, `EffectOf(commandID)` and
`OrderStatus(orderRef)`. Each effect is keyed by `command_id`, so a repeated call with the same id
is a no-op that returns the first record. The fake-only catalogue gains synthetic item codes
`FAKE-1`..`FAKE-3` (no required modifiers), so mctl-api's golden command succeeds end to end.
`SetWriteTimeoutOnce` and `SetWriteLostOnce` apply to the new writes as well. Sessions keyed by
`tenant_ref|connection_ref` are provisioned lazily with a synthetic address ref. `Revoke(key)` marks
one revoked; a revoked session gives `failed_terminal`/`provider_rejected`. There is still no `Pay`.

### Outcome map (to be copied into the runbook)

| Situation | outcome | error_code | provider_effect | Next step |
|---|---|---|---|---|
| quote / read_status ok | succeeded | none | none | submit |
| mutation applied (or deduped by command_id) | succeeded | none | applied | submit |
| schema-invalid / audience mismatch | failed_terminal | provider_rejected | none | submit if envelope valid, else drop |
| cancel_requested=true | cancelled | none | none | submit |
| kill switch / breaker open / tenant busy | failed_retryable | provider_unavailable | none | submit |
| fakestore 429 / transient read failure | failed_retryable | provider_unavailable | none | submit |
| unknown or revoked fake session, item unavailable, no order to cancel | failed_terminal | provider_rejected | none | submit |
| ambiguous write | failed_terminal | provider_unavailable | unknown | submit, never retry |
| permit `write_fence_refused` (403) | approval_refused | approval_refused | none | submit |
| permit `write_fence_unavailable` (503) | failed_retryable | internal (`error_detail=write_fence_unavailable`) | none | submit |
| permit `permit_already_issued` / `not_mutating` (409) | failed_terminal | internal (`error_detail`=code) | none | submit |
| any call `lease_stale` / `command_expired` / `command_cancelled` | - | - | - | stop, no result |
| any call `command_not_found` (404) | - | - | - | stop, metric |
| result `already_completed` or `replayed:true` | - | - | - | done |
| result `result_conflict` | - | - | - | log code + metric, no resend |
| result `invalid_document` / `binding_mismatch` / `result_inconsistent` | - | - | - | log code + metric (bug), no resend |
| result 5xx / transport | - | - | - | resend the same bytes, backoff 250ms..8s, until `expires_at` |
| permit 5xx (not 503 fence) / transport | failed_retryable | provider_unavailable | none | submit (no effect was attempted) |

Every mapping is unit-tested from a single table in `executor`. The runbook table is generated
from, or tested against, that same table, so the two cannot drift.

### Observability

`obs` keeps `NewRedactingHandler` and `Audit` (opaque refs plus a code only). It drops the Temporal
interceptor. New counters, with no id labels:
- `mctl_glovo_provider_commands_total{kind,outcome,effect}`
- `..._permits_total{result}`
- `..._results_total{status}`
- `..._result_conflicts_total`
- `..._ambiguous_writes_total`
- `..._claim_errors_total{code}`
- `..._commands_dropped_total{reason}`

`Authorization` and `lease_token` are added to the redaction key list. Logs carry `command_id`,
`execution_id` and `kind`, never `lease_token`, payload `note` or the credential.

### Health

`health.State.SetPollerRunning` becomes "last successful claim within 3 x poll interval or cap". Readiness fails
while the bridge answers 404/401/403 or is unreachable. Liveness stays process-level.

### Docs and CI

- Add `docs/runbooks/glovo-provider-worker.md`, rewritten from the #1258 copy: bridge configuration,
  the outcome map above, "default-deny egress; egress only to the mctl-api origin" as documentation
  only, the deployment gates (mctl-gitops#2457, #2506/#2540, mctl-api `MCTL_BRIDGE_ENABLED`), and a
  reuse map.
- Add `Dockerfile.glovo-provider-worker`, unchanged from #1258 except the description label
  ("command-bridge worker").
- In `build.yml`, add `go vet` / `go test -race` steps for `provider/glovo`, and the non-required
  `docker-glovo-provider-worker` job with the existing two negative runs plus a third: the worker
  must refuse to start with `TEMPORAL_HOSTPORT` set.
- No release-please, publish or GitOps change.

## Alternatives

1. **Keep the Temporal worker and add mTLS/authorizer later (merge #1258).** Dropped. Live Temporal
   1.31.0 has no TLS and no authorizer (mctl-gitops#2538), and the owner decided on 2026-11-09 that
   the bridge is canonical. A provider Temporal credential is the exposure the bridge exists to remove.
2. **Rebase #1258 in place and edit it into a bridge worker.** Dropped. The issue asks for a new PR
   and a fresh digest-bound approval. #1258's branch also predates `main`'s `internal/glovo` facade
   (its diff against `main` deletes `internal/glovo/**`), so rebasing invites accidental deletions.
   The reviewed draft stays as the reference.
3. **Hand-written validator or generated types instead of `jsonschema/v6`.** Dropped. A hand-written
   validator can drift from the pinned schemas silently. Using the same library and options as
   mctl-api makes "valid against `result.schema.json`" mean exactly what the server checks. The cost
   is one pure-Go dependency in the nested module only.
4. **Keep a provider-side `ResolveScope`/`ConsumeApproval` as defence in depth.** Dropped. The issue
   assigns scope and approval to mctl-api's stored row and write fence. A second, divergent decision
   point would be unreviewable, and the bridge exposes no endpoint for it.

## Platform impact

- **Migrations:** none. There is no database: the fakestore is in-memory.
- **Compatibility:** the root module, `cmd/server`, `cmd/glovo-mcp` and the deployed
  `labs/mctl-telegram` image are untouched; boundary tests enforce it. The new module and image are
  not published or deployed.
- **Resources:** CI gains one nested-module vet/test step and one non-required Docker build, about
  the size of #1258's.
- **Dependencies:** `provider/glovo/go.mod` drops `go.temporal.io/*`, grpc and protobuf, and adds
  `github.com/santhosh-tekuri/jsonschema/v6` (the version mctl-api pins).
- **Risks and mitigations:**
  - The wire drifts from mctl-api: SHA-256 pin, golden fixtures, the same validator library, and the
    rule in `docs/bridge.md` that the wire changes in three repos together.
  - Credential leak: the file-only source, the redacting type, slog redaction, and a leakcheck canary
    test over captured logs, errors and every request and result body sent to the fake bridge (the
    canary may appear only in the `Authorization` header).
  - Duplicate effect: dedupe by `command_id` with read-back, permit before every mutation, `unknown`
    never retried, and the result retry resends the same bytes and never re-executes.
  - Egress beyond mctl-api: the origin-pinned RoundTripper, no proxy and no redirects, tested with a
    second `httptest` server that must receive zero requests.
  - Lost in-process dedupe on restart (open question): documented as a fake-only limit. A real
    adapter needs durable dedupe; this is out of scope here.
  - Mapping mismatch with mctl-api#957: the open question blocks merge until aligned. The table lives
    in a single place in code.
