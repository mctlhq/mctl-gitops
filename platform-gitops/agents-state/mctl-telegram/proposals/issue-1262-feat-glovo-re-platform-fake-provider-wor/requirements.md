# Re-platform the private fake Glovo provider worker onto the mctl-api command bridge

## Context

mctlhq/mctl-telegram#1258 (draft, branch `feat/agents-issue-1236-feat-glovo-m1d-separate-private-fake-pro`,
head `1f1dbc197f3c187316967b0641c4ac006a2a7b0f`) builds the private fake Glovo provider as a
Temporal worker in a nested Go module `provider/glovo/`. It polls namespace
`mctl-assistants-provider-glovo` and runs `GlovoOrderWorkflow` plus activities that call a
`ControlBridge` (`ResolveScope`, `ConsumeApproval`). The canonical control-to-provider transport is
now the merged mctl-api command bridge (mctlhq/mctl-api#968, `docs/bridge.md`). It is an HTTP
claim / write-permit / result protocol over a Postgres outbox, and it gives the provider no Temporal
credential. A provider-held Temporal connection is also unsafe to deploy: the live Temporal 1.31.0
has no TLS and no authorizer (mctl-gitops#2538).

This proposal delivers the provider module in a new PR from `main`. The module carries no Temporal
SDK. Its only control-plane I/O is the bridge client: it claims commands, asks for a single-use write
permit before each mutating kind, runs the effect against the in-process `fakestore`, and posts
exactly one v1alpha1 result. mctl-api alone makes every decision about scope, tenant, owner and
approval. It needs a new, digest-bound owner approval; the #1236 approval does not carry over.
Nothing is deployed.

## User stories

- AS the platform owner I WANT the fake Glovo provider to hold no Temporal credential and to reach
  only mctl-api SO THAT the unauthenticated Temporal frontend is never exposed to a low-trust worker.
- AS the mctl-api bridge maintainer I WANT the provider to speak the vendored v1alpha1 wire byte for
  byte SO THAT a wire change is only possible through mctl-agents#1044, this issue and
  mctl-api#957 together.
- AS a security reviewer I WANT every mutation gated by a server-issued write permit and every
  ambiguous effect reported as `unknown` and never retried SO THAT no fake (and later real) order
  can be placed twice or without approval.
- AS an operator I WANT a runbook table mapping each provider-local refusal to a v1alpha1
  `outcome`/`error_code` SO THAT bridge results can be read without reading provider code.

## Acceptance criteria (EARS)

Module boundary
- THE SYSTEM SHALL keep `provider/glovo/` as a separate Go module
  (`github.com/mctlhq/mctl-telegram/provider/glovo`) with no `replace` or `require` of the root module.
- WHILE building any package of `provider/glovo/`, THE SYSTEM SHALL link no package under
  `go.temporal.io/` and no package of `github.com/mctlhq/mctl-telegram` outside `provider/glovo/`.
  A boundary test SHALL fail on either, and SHALL prove it can detect a planted import.
- THE SYSTEM SHALL contain no `internal/workflows`, `internal/activities`, `internal/bridge`
  (ResolveScope/ConsumeApproval) or `internal/basket` package, and no Temporal worker wiring in
  `cmd/glovo-provider-worker`.
- WHILE building `cmd/server` of the root module, THE SYSTEM SHALL link no package of
  `provider/glovo`, and the root `go.mod` SHALL require no `go.temporal.io` module.

Wire contract
- THE SYSTEM SHALL embed `command.schema.json`, `result.schema.json` and `PROVENANCE` byte-identical
  to mctl-api `internal/bridge/schema/`. A test SHALL pin the SHA-256 values
  `b857f62b817887f56e5fea785c36f57ede44a5647da7c5cfd7e9d5069656dae1` (command) and
  `c91bb86e973aec1c43b8af1b0743c90d23d389cfdd81e9e5b8ab6042a729354f` (result), which come from the
  mctl-agents#1045 merge `14645f93fd4eb425a3ac5adeae497209431b8342`.
- THE SYSTEM SHALL reuse mctl-api's six golden fixtures from `internal/bridge/schema/testdata/`,
  byte for byte, and SHALL assert that valid fixtures validate and invalid fixtures are rejected.
- WHEN a claimed command fails schema validation, or its `audience` differs from the configured
  worker identity, THE SYSTEM SHALL NOT execute it. IF `command_id`, `execution_id`, `lease_token`
  and `attempt` are individually well-formed, THEN THE SYSTEM SHALL submit a terminal result
  (`outcome=failed_terminal`, `error_code=provider_rejected`, `provider_effect=none`). Otherwise it
  SHALL drop the command and increment a metric.
- WHEN THE SYSTEM builds a result, THE SYSTEM SHALL validate it against `result.schema.json` before
  sending. IF validation fails, THEN THE SYSTEM SHALL NOT send it and SHALL count an internal error.

Bridge client
- WHEN polling, THE SYSTEM SHALL `POST {base}/api/v1/bridge/commands/claim` with body `{"max": n}`,
  where 1 <= n <= 10, and SHALL accept only a response `{"schema_version":"bridge.mctl.ai/v1alpha1","commands":[...]}`
  or, for a provider served v1alpha2 commands (round 7), `{"schema_version":"bridge.mctl.ai/claim/v1alpha2","commands":[...]}`.
- WHEN a claimed command is a v1alpha2 `place_order_fake` (mctl-agents#1059 §Write command), THE SYSTEM
  SHALL validate it against that schema, run it through the same permit/effect/result path as the
  v1alpha1 mutating kinds (fake only), and answer with the v1alpha1 result. A v1alpha2 command of any
  other kind SHALL be refused locally as invalid. A provider that does not declare v1alpha2 SHALL never be
  handed that command (mctl-api#986 §2a); this issue's test proves it with the fake bridge (task 2b). (round 7)
- IF a claim response has a missing, null or non-array `commands`, a wrong `schema_version`, any
  extra top-level field, trailing data after the JSON value, or a body that reaches the 64 KiB cap,
  THEN THE SYSTEM SHALL treat it as a failed claim (error + `claim_errors_total{code="malformed"}`),
  never as an empty batch.
- IF a claimed command carries no `lease_token` (the field is optional in `command.schema.json`),
  THEN THE SYSTEM SHALL drop it without executing it and increment
  `commands_dropped_total{reason="no_lease_token"}`.
- IF any bridge response is a status/code pair not listed in the runbook outcome map, has no
  parseable `{"code"}` body, or is otherwise unparseable, THEN THE SYSTEM SHALL fail closed: no
  effect, no result with a different body, and the response SHALL count as a failed read, never as
  success or an empty result.
- WHEN any bridge route answers 429 (httprate, 120 requests/min per principal, no `code` body),
  THE SYSTEM SHALL handle it per route: claim backs off honouring `Retry-After`; permit performs no
  effect and reports `failed_retryable`/`provider_unavailable`/`none`; result resends the same bytes.
  The default poll interval, claim batch and retry backoff SHALL keep one worker below 120
  requests/min in steady state.
- WHEN a claimed command has kind `place_order_fake` or `cancel_order_fake`, THE SYSTEM SHALL
  `POST {base}/api/v1/bridge/commands/{command_id}/write-permit` with `{"lease_token": ...}`, and
  SHALL run the effect only after a 200 permit response.
- WHEN a claimed command has kind `quote` or `read_status`, THE SYSTEM SHALL NOT request a write permit.
- WHEN a command completes, THE SYSTEM SHALL `POST {base}/api/v1/bridge/commands/{command_id}/result`
  exactly one result document per (command_id, lease_token).
- THE SYSTEM SHALL read the bearer credential only from the file named by
  `MCTL_BRIDGE_CREDENTIAL_FILE`. It SHALL never accept the credential from an environment value and
  SHALL never write it to a log, error, metric label or result.
- THE SYSTEM SHALL send requests only to the configured `MCTL_API_BASE_URL` origin. Any request to
  another scheme, host or port SHALL be refused before dialing. The client SHALL also follow no
  redirects and use no HTTP proxy.

Execution semantics
- THE SYSTEM SHALL make no scope, tenant, owner or approval decision of its own; the command's stored
  row and the server write fence are authoritative.
- WHEN a mutating command is executed, THE SYSTEM SHALL apply it only to the in-process `fakestore`,
  keyed by `command_id`, and SHALL read the effect back before reporting `provider_effect=applied`.
- WHEN a mutating command's `command_id` already has a local effect record in the `fakestore`
  (confirmed or ambiguous; this happens only after a reclaim, which turns server `effect_state`
  `permitted` into `unknown`), THE SYSTEM SHALL request no permit, perform no second effect, and
  report `outcome=failed_terminal`, `error_code=internal`, `provider_effect=unknown`,
  `error_detail=applied_prior_lease`. It SHALL NOT report `applied`, which mctl-api refuses with 422
  `result_inconsistent` unless `effect_state == permitted`.
- IF a fakestore write is ambiguous (timeout or error and the read-back does not confirm it applied),
  THEN THE SYSTEM SHALL report `provider_effect=unknown` with `outcome=failed_terminal`, and SHALL
  never retry that effect.
- IF the permit request returns `write_fence_refused` (403), `write_fence_unavailable` (503) or
  `not_mutating` (409), THEN THE SYSTEM SHALL perform no effect and SHALL report the outcome mapped
  in the runbook table with `provider_effect=none`.
- IF the permit request returns `permit_already_issued` (409), THEN THE SYSTEM SHALL perform no
  effect and SHALL report `outcome=failed_terminal`, `error_code=internal`,
  `provider_effect=unknown`, `error_detail=permit_already_issued`. The server returns this code only
  when `effect_state != none`, i.e. a previous lease already held a permit, so an effect may exist
  that this process cannot observe. (Owner decision 2026-11-09, overriding the issue text
  `provider_effect=none`.)
- IF any bridge call returns `lease_stale`, `command_expired` or `command_cancelled`, THEN THE SYSTEM
  SHALL stop work on that command, perform no effect, and send no further request for it.
- WHEN a claimed command has `cancel_requested=true`, THE SYSTEM SHALL NOT execute it and SHALL
  report `outcome=cancelled`, `provider_effect=none`. (Defensive: unreachable on mctl-api
  `a9ca5814`, because `Cancel` sets `status=cancelled` and claim selects only `pending` or expired
  `leased` rows. The runbook SHALL label it unreachable.)
- WHEN the result call returns a 200 with `replayed:true`, THE SYSTEM SHALL treat the command as
  done. An `already_completed` code on the result route is handled the same way defensively; it is
  unreachable on mctl-api `a9ca5814` (only control-side `Cancel` returns it) and SHALL be labelled
  unreachable in the runbook.
- IF the result call returns `result_conflict`, THEN THE SYSTEM SHALL log the code (never the body),
  increment `mctl_glovo_provider_result_conflicts_total`, and SHALL NOT resend with a different body.
- IF the result call fails with 5xx, 429 or a transport error, THEN THE SYSTEM SHALL retry the same
  bytes with bounded exponential backoff until success, a terminal code, `lease_stale`, or the
  command's `expires_at`. It SHALL never re-execute the command. The permit request and the effect
  are bounded by the lease deadline (claim time + lease TTL - margin); result retries alone are
  bounded by `expires_at`, because mctl-api accepts a replay with the same lease token after the
  lease ran out (completed check precedes `leaseLive`, `store.go:768-776`).
- WHILE the kill switch `GLOVO_PROVIDER_DISABLED=true` is set, THE SYSTEM SHALL request no permit
  and perform no effect, and SHALL report claimed commands as `failed_retryable` /
  `provider_unavailable` / `none`.

Retained gates
- THE SYSTEM SHALL keep the `fakeonly` build tag and the `FAKE_ONLY=true` runtime gate, including
  the `GLOVO_*` credential-name deny list. It SHALL also keep the `fakestore`, `fairness`,
  `leakcheck`, `obs` redaction and `health` packages, the distroless non-root
  `Dockerfile.glovo-provider-worker`, and a non-required `docker-glovo-provider-worker` CI job with
  negative image runs.
- WHEN any test runs the worker with a canary credential, THE SYSTEM SHALL produce no log line,
  error or result that contains the canary.

## Out of scope

- Any deployment, GitOps manifest, image publication, release-please job, network policy object or
  credential issuance.
- Enabling `MCTL_BRIDGE_ENABLED` or changing mctl-api.
- Choosing the provider credential issuer (gated on mctl-gitops#2506/#2540).
- Any change to the v1alpha1 wire (that requires mctl-agents#1044, this issue and mctl-api#957 together).
  The v1alpha2 write is defined in mctl-agents#1059, not here; this issue only vendors and executes it.
- A real Glovo API, login, basket, checkout or payment.
- Changes to the root module, `cmd/server`, `cmd/glovo-mcp` or `internal/glovo`.

## Open questions

- Resolved (amendment 2026-11-09): the provider outcome map is **final within the frozen
  `result.schema.json` enums**. It needs no new wire value: bridge codes without an enum go to
  `error_code=internal` with the code in `error_detail`. The map is posted to mctlhq/mctl-api#957
  for its refusal table; it is not a merge gate of this PR, because #957 governs the facade↔API
  refusal set, not the v1alpha1 result enums. A wire change still requires #1044, this issue and
  #957 together.
- Resolved (owner decision 2026-11-09): `permit_already_issued` reports `provider_effect=unknown`,
  not `none` as the issue text said. A restarted worker has no local record of an effect a previous
  lease holder may have applied, so `none` would assert an absence it cannot observe.
- Fake connection sessions. `fakestore` refuses an unknown session. To keep the fake exercisable,
  this proposal auto-provisions a synthetic session per (`tenant_ref`, `connection_ref`) on first
  use, and lets tests revoke one. The reviewer should confirm that is acceptable, rather than
  refusing all commands as #1258 did.
- Port source. The new PR must port retained packages from the #1258 branch head `1f1dbc19`. If
  that ref becomes unreachable, the implementer must rebuild them from the descriptions in design.md.
- Deployed state of mctl-api (whether `MCTL_BRIDGE_ENABLED` is set) could not be observed from the
  mounted gitops checkout; see design.md.
