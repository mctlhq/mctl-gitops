# Tasks: issue-1262-feat-glovo-re-platform-fake-provider-wor

Branch from `main`. Source for ported packages: the #1258 branch
`feat/agents-issue-1236-feat-glovo-m1d-separate-private-fake-pro` at `1f1dbc197f3c187316967b0641c4ac006a2a7b0f`.
Check out only `provider/glovo/**`, `Dockerfile.glovo-provider-worker` and
`docs/runbooks/glovo-provider-worker.md` from it, using `git checkout <sha> -- <paths>`. Never merge
or rebase that branch: its tree deletes `main`'s `internal/glovo/**`.

- [ ] 1. Port the retained packages: `fakeonly`, `fakestore`, `fairness`, `leakcheck`, `obs`
  (redact + audit), `health` and `testkit` if still used. Also port `go.mod` and the Dockerfile.
  Do not port `internal/workflows`, `internal/activities`, `internal/bridge`, `internal/bridge/fake`
  or `internal/basket`. Remove the Temporal interceptor from `obs/obs.go`. — DoD: in
  `provider/glovo`, `go build ./...` passes; `go mod tidy` leaves no `go.temporal.io` line in
  `go.mod`/`go.sum`; `git diff main --stat` touches no root-module file except `build.yml` and the
  runbook.
- [ ] 2. Replace the contents of `internal/protocol/v1alpha1` with the bridge wire (depends on 1).
  Byte-copy `command.schema.json`, `result.schema.json`, `PROVENANCE` and `testdata/*.json` from
  mctl-api `internal/bridge/schema/`. Add `wire.go` with `Command`, `Payload`, `Result`,
  `ClaimResponse`, `ParseCommand` (schema then strict decode, plus best-effort `Envelope`) and
  `EncodeResult` (marshal then validate), using `santhosh-tekuri/jsonschema/v6` with
  `AssertFormat()`. Delete `ProviderRequest`. — DoD: the files' sha256 values are `b857f62b...6dae1`
  and `c91bb86e...354f`; the wire tests pass.
- [ ] 3. Extend `fakestore` (depends on 1). Add the synthetic `FAKE-1..FAKE-3` catalogue codes,
  `PlaceOrderFake` and `CancelOrderFake` keyed by `command_id` (idempotent), `EffectOf(commandID)`,
  `OrderStatus(orderRef)`, lazy session provisioning per `tenant_ref|connection_ref` and
  `Revoke(key)`. Existing write-fault knobs apply to the new writes. There is still no `Pay`.
  — DoD: unit tests cover dedupe, timeout-after-apply, lost write and revoked session.
- [ ] 4. Add `internal/bridgeclient`: `credential.go`, `transport.go` and `client.go` with
  `Claim` / `WritePermit` / `SubmitResult` and `*APIError{Status, Code, RetryAfter}` (depends on 2).
  A code-less error body gives `Code=""`; the claim response is strictly decoded (exact fields, no
  trailing data, `commands` a non-null array, 64 KiB cap = error). — DoD:
  an `httptest` test passes for each route; a request to another origin is refused before dialing;
  redirects and proxy env are ignored; the credential is re-read per request and never formatted;
  each malformed claim body is an error, never an empty batch.
- [ ] 5. Add `internal/executor` (depends on 2, 3). It holds the single outcome-map table from
  design.md and turns a parsed command plus a permit result into a `Result`. It enforces read-back
  before `applied`, returns `unknown` on an ambiguous write, on `permit_already_issued` and on any
  pre-existing local effect record (`applied_prior_lease`), and fails closed on any unmapped
  status/code. — DoD: a table-driven test covers every row of the map.
- [ ] 6. Add `bridgeclient/poller.go` (depends on 4, 5). It implements the claim loop with jittered
  backoff honouring `Retry-After`, the per-command state machine (parse, pre-flight, optional
  permit, execute, encode once, submit with retry of the same bytes), two deadlines (lease deadline
  for permit + effect, `expires_at` for result retries), the per-tenant `fairness.Limiter`, and
  stop-on-`lease_stale`/`command_expired`/`command_cancelled`/`command_not_found`. — DoD: poller
  tests against `bridgefake` pass with `-race`.
- [ ] 7. Add `bridgeclient/bridgefake` (depends on 2). This is an `httptest` bridge with claim,
  permit and result state: tenants and audience per credential, lease TTL and epoch, reclaim with a
  new token, `expires_at`, cancel, the permit fence modes (allow / refuse / unavailable /
  already-issued), result schema validation with the vendored schema, the
  `worker_identity`/`execution_id`/`attempt` binding check, a replay digest returning
  `replayed:true` (also after lease expiry with the same token), `result_conflict`, injectable 5xx,
  injectable code-less 429 (with `Retry-After`) and 401 bodies, malformed claim bodies, and a
  request recorder. It MUST model mctl-api's effect rules: reclaim and cancel turn `permitted` into
  `unknown`; `applied` without `permitted` returns 422 `result_inconsistent`; a permit when
  `effect_state != none` returns 409 `permit_already_issued`. — DoD: the fake's own tests assert
  each server rule listed in design.md "Current state" and these three effect rules.
- [ ] 8. Rewrite `cmd/glovo-provider-worker` (depends on 6). `config.go` reads the bridge settings and
  refuses any `TEMPORAL_*` variable; `main.go` runs gates, health and the poller, with graceful stop
  bounded by `WORKER_STOP_TIMEOUT`. — DoD: `main_test.go` covers each startup refusal; the worker
  starts against `bridgefake` and shuts down on SIGTERM.
- [ ] 9. Add the boundary tests in `cmd/glovo-provider-worker/boundary_test.go` (depends on 8). One
  checks `go list -deps ./...` in the module for any `go.temporal.io/` package or any
  `github.com/mctlhq/mctl-telegram/` package outside `.../provider/glovo/`. One checks
  `go list -m all` for any `go.temporal.io` module. One proves the checker detects planted imports.
  Keep the #1258 root check (`cmd/server` does not link the provider; root `go.mod` has no Temporal).
  — DoD: the tests pass, and fail when a temporal import is planted locally.
- [ ] 10. Docs and CI (depends on 8). Add `docs/runbooks/glovo-provider-worker.md` with the bridge
  config, the outcome table (asserted equal to the executor table by a test), "egress to mctl-api
  only", the deployment gates and the stop conditions. Update the Dockerfile label. In `build.yml`,
  add the `provider/glovo` vet and race-test steps and the non-required `docker-glovo-provider-worker`
  job: non-root check, refuse without `FAKE_ONLY`, refuse with `GLOVO_SESSION_TOKEN`, refuse with
  `TEMPORAL_HOSTPORT`. — DoD: CI is green; no release/publish job was added.
- [ ] 11. Open the PR from `main`, referencing #1262, #1236, mctl-api#968, mctl-agents#1044,
  mctl-api#957 and mctl-gitops#2457, with a note to close #1258 as superseded on merge. Use the merge
  strategy `--merge`. — DoD: the PR body states that the outcome map is final within the frozen
  `result.schema.json` enums, and the map is posted as a comment on mctl-api#957 before merge.

## Tests

- [ ] T1. Schema pin: the sha256 of both vendored schemas equals the pinned digests, and `PROVENANCE`
  names them and merge `14645f93`.
- [ ] T2. Golden fixtures: `command.valid` / `result.valid` pass; `command.extra-field`,
  `command.bad-ref-pattern`, `command.mutation-missing-approval` and `result.extra-field` are rejected.
- [ ] T3. Schema-invalid command (for example the bad-ref fixture with a valid envelope) is not
  executed: zero fakestore writes and a `failed_terminal`/`provider_rejected`/`none` result. With an
  invalid envelope, no result is sent and the dropped metric is incremented.
- [ ] T4. A result carrying an extra field is refused by `EncodeResult` and never sent (the fake
  records zero result posts).
- [ ] T5. Happy path for each kind: `quote` and `read_status` make zero permit calls and report
  effect `none`; `place_order_fake` and `cancel_order_fake` make exactly one permit call, then one
  effect, then `applied`.
- [ ] T6. Wrong audience or foreign tenant: the claim never returns the command, and a direct
  permit/result returns `command_not_found`. The worker stops with no effect. A claimed command with
  a mismatched `audience` is refused locally.
- [ ] T7. Stale lease after reclaim: the fake reclaims under epoch+1 mid-execution. The old holder's
  permit or result gets `lease_stale`, the worker stops, and no second effect occurs.
- [ ] T8. Result replay: the fake fails the first result with 503 after storing it. The worker
  resends identical bytes, the fake answers `replayed:true`, and the effect count stays 1.
- [ ] T9. Result 5xx and transport error: the same bytes are retried with backoff until success. The
  command is never re-executed, and retries stop at `expires_at`.
- [ ] T10. `result_conflict`: the conflict metric is incremented, there is no resend, and the log
  carries the code only.
- [ ] T11. Permit refused, one subtest each for `write_fence_refused`, `write_fence_unavailable`,
  `permit_already_issued` and `not_mutating`. Each has zero effects and the mapped
  outcome/error_code. `provider_effect` is `none`, except `permit_already_issued`, which is
  `unknown` (owner decision 2026-11-09).
- [ ] T12. Ambiguous write: `SetWriteLostOnce`, and separately `SetWriteTimeoutOnce`. The lost write
  gives `failed_terminal`/`unknown` with no second effect attempt and the ambiguous metric
  incremented. Timeout-after-apply is confirmed by read-back, giving `applied`.
- [ ] T13. Re-delivery after reclaim: the fake grants a permit, the worker applies the effect, the
  lease expires and the fake reclaims (server `effect_state` `permitted -> unknown`). The re-claimed
  command gives `failed_terminal`/`internal`/`unknown` with `error_detail=applied_prior_lease`, no
  permit call, no second write, and the fake accepts the result (no 422).
- [ ] T14. `cancel_requested=true` (defensive, injected by the fake only), an expired command,
  `command_cancelled` and `command_expired` all produce no effect, with the expected result or no
  result.
- [ ] T15. Kill switch and breaker: no permit, no effect, `failed_retryable`/`provider_unavailable`.
- [ ] T16. Credential canary: the credential file holds a `leakcheck` canary. Captured logs, errors,
  metric output and every recorded request body contain no canary. The fake asserts it saw the
  canary only in `Authorization`. Missing or empty file: startup fails naming the setting only.
- [ ] T17. Egress: with a base URL pointing at fake A, a planted request to fake B is refused; B
  records zero requests. A 302 from A to B is not followed. `HTTPS_PROXY` set causes no proxy use.
- [ ] T18. Config: non-origin base URL, non-loopback `http`, out-of-range claim max, a bad worker
  identity and any `TEMPORAL_*` variable are each refused.
- [ ] T19. Boundary: no Temporal and no root-module import in `provider/glovo`; `cmd/server` does not
  link the provider; the planted-import detector works.
- [ ] T20. Retained gates: the `fakeonly` build-tag and runtime tests, and the CI negative image
  runs (no `FAKE_ONLY`, `GLOVO_SESSION_TOKEN`, `TEMPORAL_HOSTPORT`).
- [ ] T21. Mutation check for T13 and the fake's effect rules: with step 4.1 reverted to "report
  `applied`", T13 fails on the fake's 422; with the fake's reclaim rule removed, the fake's own test
  fails. Record both in the PR body.
- [ ] T22. 429 per route: claim waits at least `Retry-After`; permit 429 gives no effect and
  `failed_retryable`/`provider_unavailable`/`none`; result 429 resends identical bytes. The steady
  request rate at defaults stays under 120/min.
- [ ] T23. Fail closed: a code-less 401, an unmapped status/code and an unparseable error body each
  give no effect and no result with a different body, and increment `unmapped_responses_total` or
  stop as mapped.
- [ ] T24. Malformed claim: missing `commands`, `"commands": null`, a non-array `commands`, an extra
  top-level field, trailing data and a body at the 64 KiB cap are each a claim error, not an empty
  batch; a command without `lease_token` is dropped with the metric and not executed.
- [ ] T25. Deadlines: a result retry continues past the lease deadline and succeeds as a same-token
  replay before `expires_at`; a permit is never requested after the lease deadline; `lease_stale`
  stops result retries.

## Rollback

The change is additive: a new nested module, a Dockerfile, a runbook and non-required CI steps. It
deploys nothing and touches no root-module runtime code. To roll back, revert the merge commit
(`git revert -m 1 <merge-sha>`). Nothing needs undoing in GitOps, Vault, Temporal or mctl-api, since
no credential was issued and `MCTL_BRIDGE_ENABLED` was not touched. #1258 remains available as the
reviewed draft reference until this PR merges; close it only after the merge.
