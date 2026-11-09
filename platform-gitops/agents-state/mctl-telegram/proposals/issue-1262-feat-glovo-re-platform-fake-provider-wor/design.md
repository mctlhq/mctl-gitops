# Design: issue-1262-feat-glovo-re-platform-fake-provider-wor

## Amendment 2026-11-09 (round 7): the v1alpha2 `place_order_fake`

Class A of the Glovo M1 seam review. The Glovo `place_order_fake` is the one v1alpha2 write
(mctl-agents#1059 §Write command defines it; mctl-api#986 §2a owns the wire version, projection,
Claim gating and vendoring). This issue owns parsing and executing it, fake only. Everything else
in this proposal (the v1alpha1 wire, `cancel_order_fake`, `quote`, `read_status`) is unchanged.
See "Wire", "Bridge client" and task 2b below.

## Amendment 2026-11-09

Resolves the independent pre-approval review on mctlhq/mctl-telegram#1262 (comment 6740949177).
Every cited server line was re-read on mctl-api `a9ca5814`.

| Finding | Change |
|---|---|
| P1: after a reclaim, `applied` is always refused (`store.go:637` reclaim and `store.go:830-831` cancel turn `permitted` into `unknown`; `store.go:783-784` accepts `applied` only from `permitted`) | State machine step 4.1 and the map: a `command_id` with any local effect record reports `failed_terminal`/`internal`/`unknown`, `error_detail=applied_prior_lease`, no permit. `bridgefake` models reclaim/cancel `permitted -> unknown`, 422 for `applied` without `permitted`, and `permit_already_issued` for `effect_state != none`. T13 rewritten; T21 mutation check |
| P2: 429 and code-less error bodies undefined (`router.go:881`, `bridgeClaimPerMin=120` at `handlers_bridge.go:43`; 401 via `writeError` `{"error"}` at `handlers_bridge.go:75`, `handlers_read.go:1002`) | Client: `APIError` keeps `Code=""` for a code-less body; map rows for claim/permit/result 429 and 401; any unmapped status/code or unparseable body fails closed. Rate budget documented. T22, T23 |
| P2: `permit_already_issued` reported as `none` (`permit.go:103-104`) | Owner decision 2026-11-09: `failed_terminal`/`internal`/`unknown`, `error_detail=permit_already_issued`. T11 updated |
| P3: result-retry bound contradicts itself | Two deadlines: lease deadline for permit + effect, `expires_at` for result retries only (`store.go:768-776` accepts a same-token replay after lease expiry); stop on `lease_stale` |
| P3: claim response fail-closed | Malformed claim body (missing/null/wrong-typed `commands`, extra field, trailing data, 64 KiB cap) is a claim error, never an empty batch; a command without `lease_token` is dropped + metric. T24 |
| P3: unreachable branches | `already_completed` on result and `cancel_requested=true` on a claimed command are kept as defence and labelled unreachable on `a9ca5814` (`store.go:827` is the only `ErrAlreadyCompleted`, in control-side `Cancel`; claim selects only `pending`/expired-`leased`, `store.go:595-597`) |
| P3: soft mctl-api#957 gate | The map is declared final within the frozen `result.schema.json` enums and posted to #957; task 11 DoD changed accordingly |

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
- The v1alpha2 write (round 7, task 2b). The provider vendors `command-place-order-fake.schema.json`,
  `approval-basket.schema.json` and `claim-response.schema.json` from mctl-agents#1059 (the files and
  digests of its `SHA256SUMS`, copied byte for byte, with the sha256 pinned in `wire_test.go`).
  `ParseCommand` dispatches on `schema_version`: `bridge.mctl.ai/v1alpha1` validates against the
  command schema above; `bridge.mctl.ai/v1alpha2` is accepted ONLY with `kind == place_order_fake`
  and validates against the write schema; any other combination (a v1alpha2 read kind, a v1alpha2
  `cancel_order_fake`, a v1alpha1 `place_order_fake` carrying an approval basket) is `ErrInvalid`.
  The v1alpha2 `payload` is the approval basket; the fake stores its `item_codes` and quantities and
  nothing else. The result is the unchanged v1alpha1 `result.schema.json` (#1059 §Write command,
  "Result"): `EncodeResult` is not versioned. `cancel_order_fake` stays v1alpha1.
- `wire_test.go` checks:
  - `sha256(schema/*.json)` equals the pinned digests (the two v1alpha1 ones and, round 7, the three
    vendored from #1059);
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
  A non-2xx response decodes `{"code"}` into `*APIError{Status, Code}` and never keeps the body.
  A body without a parseable `code` (httprate's 429, the `writeError` 401 `{"error"}`, a proxy page)
  gives `Code=""`; the caller maps by status only for the rows below and fails closed otherwise.
  `Retry-After` (seconds) is kept on the error for 429.
- Claim response: strict decode of exactly `{"schema_version","commands"}` with
  `DisallowUnknownFields` and no trailing data; `schema_version` is `bridge.mctl.ai/v1alpha1` or, when
  mctl-api serves this provider v1alpha2 commands, `bridge.mctl.ai/claim/v1alpha2` (#1059 §Claim
  response; each element is then validated by its own `schema_version`); any other value is a failed
  claim; `commands` present and an array (`null` is an error). A body reaching the 64 KiB cap is an error.
  Any failure is a claim error (`claim_errors_total{code="malformed"}`), never an empty batch. A
  command without `lease_token` is dropped with `commands_dropped_total{reason="no_lease_token"}`.
- Poller: on a claim error, back off exponentially with jitter (cap 60s). A claim 429 waits at
  least `Retry-After`. A claim 404 (bridge disabled) or 401/403 (`bridge_provider_required`/
  `bridge_provider_gate`) keeps the readiness probe failing and backs off at the cap. Each claimed
  command runs in its own goroutine, bounded by `fairness.Limiter` per `tenant_ref` and by the claim
  batch.
- Deadlines: the permit request and the effect run under a context ending at the **lease deadline**
  `min(expires_at, claim time + lease TTL 60s - 5s margin)`. Result submission (including retries of
  the same bytes) runs under a separate context ending at `expires_at`, since mctl-api accepts a
  same-token replay after the lease ran out (`store.go:768-776`). `lease_stale` stops both.
- Rate budget: the bridge allows 120 requests/min per principal across all three routes
  (`router.go:881`). Defaults (poll 2s = 30 claims/min, batch 4, at most one permit and one result per
  command) stay under it at a steady 10 commands/min; above that the claim interval is stretched
  by the observed 429s. The runbook states the budget.

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
4. Mutating kinds (`place_order_fake` in either wire version, `cancel_order_fake`). The provider is
   handed a v1alpha2 `place_order_fake` only if it is configured to declare `bridge.mctl.ai/v1alpha2`
   (mctl-api#986 §2a, Claim gating); a provider that does not is never handed that command, and a
   v1alpha2 command arriving anyway is refused locally by `ParseCommand` as above:
   1. Read back `fakestore.EffectOf(command_id)`. If any local effect record exists (confirmed or
      ambiguous), the command came back after a reclaim, and the server has already turned
      `effect_state` `permitted` into `unknown` (`store.go:637`; cancel at `store.go:830-831`).
      Report `failed_terminal`/`internal`/`unknown` with `error_detail=applied_prior_lease`; no
      permit, no second effect. Never report `applied` here: `SubmitResult` refuses it unless
      `effect_state == permitted` (`store.go:783-784`).
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
| mutation applied under this lease's permit | succeeded | none | applied | submit |
| mutation re-delivered after reclaim, local effect record exists | failed_terminal | internal (`error_detail=applied_prior_lease`) | unknown | submit, no permit |
| schema-invalid / audience mismatch | failed_terminal | provider_rejected | none | submit if envelope valid, else drop |
| cancel_requested=true | cancelled | none | none | submit |
| kill switch / breaker open / tenant busy | failed_retryable | provider_unavailable | none | submit |
| fakestore 429 / transient read failure | failed_retryable | provider_unavailable | none | submit |
| unknown or revoked fake session, item unavailable, no order to cancel | failed_terminal | provider_rejected | none | submit |
| ambiguous write | failed_terminal | provider_unavailable | unknown | submit, never retry |
| permit `write_fence_refused` (403) | approval_refused | approval_refused | none | submit |
| permit `write_fence_unavailable` (503) | failed_retryable | internal (`error_detail=write_fence_unavailable`) | none | submit |
| permit `permit_already_issued` (409) | failed_terminal | internal (`error_detail=permit_already_issued`) | unknown | submit (owner decision 2026-11-09) |
| permit `not_mutating` (409) | failed_terminal | internal (`error_detail=not_mutating`) | none | submit |
| permit 429 | failed_retryable | provider_unavailable | none | submit (no effect attempted) |
| any call `lease_stale` / `command_expired` / `command_cancelled` | - | - | - | stop, no result |
| any call `command_not_found` (404) | - | - | - | stop, metric |
| result `replayed:true` | - | - | - | done |
| result `already_completed` (unreachable on `a9ca5814`; defence only) | - | - | - | done |
| result `result_conflict` | - | - | - | log code + metric, no resend |
| result `invalid_document` / `binding_mismatch` / `result_inconsistent` | - | - | - | log code + metric (bug), no resend |
| result 5xx / 429 / transport | - | - | - | resend the same bytes, backoff 250ms..8s (429: at least `Retry-After`), until `expires_at` |
| claim 429 | - | - | - | back off at least `Retry-After` |
| any call 401 (`{"error"}`, no code) | - | - | - | stop the command, readiness fails, claim backs off at cap |
| any other status/code, or unparseable body | - | - | - | fail closed: no effect, no new body, metric `unmapped_responses_total{route}` |
| permit 5xx (not 503 fence) / transport | failed_retryable | provider_unavailable | none | submit (no effect was attempted) |

The `cancel_requested=true` pre-flight row and the result `already_completed` row are unreachable on
mctl-api `a9ca5814`; the runbook labels them "unreachable (defence)" so nobody reads them as
tested server behaviour.

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
  - Lost in-process dedupe on restart: covered by reporting `unknown` on `permit_already_issued`
    (owner decision 2026-11-09). A real adapter still needs durable dedupe; out of scope here.
  - Mapping mismatch with mctl-api#957: the map is final within the frozen `result.schema.json`
    enums and is posted to #957; the table lives in a single place in code.
