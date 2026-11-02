# Tasks: issue-1090-feat-agentapi-pool-credential-and-manage

- [ ] 1. Identity and pool provider: add `auth.Identity.Pool` + `IsPool()`
  (`internal/auth/identity.go`); add `internal/auth/localjwt/pool.go` with
  `PoolAudience`, `ValidPoolName`, `PoolProvider`/`NewPoolProvider`
  (Bearer only, audience required, shape check, mandatory revocation check,
  no `EnsureUserByTelegramID`); add `"agent-pool"` to `derivedAudiences` in
  `issuer.go`. — DoD: a valid pool token yields `UserID=0, TelegramID=0,
  Pool=<name>, Jti, OriginalIssuedAt`; every shape violation listed in
  requirements is 401; `NewPoolProvider` refuses a nil revocation cache.
- [ ] 2. Revocation helper: `RevocationCache.IsBlanketRevoked(ctx, tgID, issuedAt)`
  in `revocation.go`, sharing refresh/fail-closed logic with `IsRevoked`.
  — DoD: unit test for revoked/not-revoked/cold-cache-error.
- [ ] 3. Shared jti generator: export `workertoken.GenerateJti` (keep the
  unexported name as an alias call). — DoD: existing workertoken tests pass.
- [ ] 4. Mint route `internal/agentapi/pooltokenhandler.go`
  (`NewPoolTokenHandler`), TTL clamped in hours (30 d default, 90 d cap),
  strict decode, name validation, `pool token minted` log line in the
  `LogMinted` key shape, response `{pool_token, expires_at, jti}`
  (depends on 1, 3). — DoD: handler tests for 401/403/400/clamp/overflow and
  the decoded claims.
- [ ] 5. Config: `ManagedMaxInflightPerAccount` from
  `MANAGED_MAX_INFLIGHT_PER_ACCOUNT` (default 1, >= 1) in
  `internal/config/config.go`. — DoD: config test for default and invalid.
- [ ] 6. Schema and store: `agent_jobs.runtime` column (`agent_schema.go`);
  `AgentJob.Runtime` scanned everywhere `agentJobCols`/RETURNING are used;
  `ClaimAgentJobs(..., runtime, limit)` and `claimCoalesced(..., runtime, limit)`
  with the COALESCE predicate in both candidate selections and `runtime = $n`
  in both UPDATEs; reject a runtime other than own/managed;
  `Queue.Claim(ctx, userID, runtime, limit)`; update all callers.
  — DoD: `go build ./...` and existing claim tests green with `RuntimeOwn`.
- [ ] 7. `ListManagedClaimCandidates` in `internal/db/agent_managed_claim.go`
  (managed, current consent, due pending, telegram_login_id, below in-flight
  cap, oldest first, limit; budget seam comment for #1092) (depends on 6).
  — DoD: store tests on SQLite and, where the suite supports it, Postgres.
- [ ] 8. Claim-only guard: `requireNotPool` in `binding.go` (403
  `pool_credential_claim_only`, slog warn, policy-denial metric, audit under
  the job owner when a `{id}` job resolves via new `Store.AgentJobOwner`);
  `Register` wraps every route except `POST /jobs/claim` outside `toolGate`
  (depends on 1). — DoD: route-table test passes; no `audit_logs` insert with
  user id 0.
- [ ] 9. Pool claim branch in `events.go`: `handlePoolClaim` (503 without
  signer, candidate loop, blanket-revocation skip, render-before-claim per
  account, `Claim(..., RuntimeManaged, 1)`, round robin one job per account,
  release on mint failure via `RetryAgentJob`, audit under the job user with
  `pool:<name>`); `mintJobToken` takes Subject/TelegramID from
  `Store.TelegramIDByUserID` for a pool parent and keeps the pool's
  jti/orig_iat; account branch passes `RuntimeOwn` and is otherwise unchanged;
  `Server.WithManagedClaims` (depends on 2, 6, 7, 8).
  — DoD: all `TestHandleClaimJobs_Pool_*` tests pass.
- [ ] 10. Server wiring in `cmd/server/main.go`: under
  `cfg.ManagedRuntimeEnabled && cfg.OAUTHJWTSecret != ""` mount
  `POST /api/agent/pool-token`, chain `selectAgentPoolProvider` after the agent
  and job providers, call `agentSrv.WithManagedClaims` (depends on 4, 9).
  — DoD: flag off -> mint route 404 and pool token 401; flag on -> claim works.
- [ ] 11. Runtime switch fence: `RuntimeChange.Apply` sets
  `BumpInstallRevision` when the runtime actually changes
  (`internal/assistantinstall/runtime.go`). — DoD:
  `TestRuntimeSwitch_FencesInflightJob` passes through the admin profile route
  and through `update_install`.
- [ ] 12. Worker pool mode: parse `AGENT_POOL_MODE` in
  `cmd/agent-worker/main.go`; `PoolMode` on `ClaudeInvoker` and
  `OpenAIRunner`; in pool mode `mcpToken` never falls back, a job without a
  token fails with the shared `errNoJobToken`, and `finishRun` runs on a client
  with the job token; outside pool mode unchanged. — DoD: worker tests below
  pass; existing worker tests unchanged.
- [ ] 13. Docs touch-up in `docs/adr/0008-managed-runtime.md` only where code
  diverges (e.g. `IsBlanketRevoked`, refusal audit via slog), plus
  `MANAGED_MAX_INFLIGHT_PER_ACCOUNT` and `AGENT_POOL_MODE` in the env docs.
  — DoD: ADR matches code.

## Tests

Every test must fail with the bug reintroduced; the PR states the mutation for
each.

- [ ] T1. `TestClaimAgentJobs_RuntimePredicate` (`internal/db`), subtests for
  the plain path and the coalesced path (`WithTurnCoalescing`): own claims only
  own, managed only managed, profile-less claimed as own, and
  `agent_jobs.runtime` stamped. Mutation: drop the predicate from either query
  (each subtest fails independently).
- [ ] T2. `TestPoolRevocation_KillsIssuedJobToken` (`internal/agentapi` with
  the real chained providers and a `RevocationCache` on a controllable clock):
  mint pool -> claim -> derived job token -> `RevokeWorkerToken(pool jti)` ->
  advance past the 15 s TTL -> `propose_reply` with the existing job token is
  401, and the pool's claim is 401. Mutation: skip the jti check for
  `agent-job` in `needsRevocationCheck`/`Authenticate`.
- [ ] T3. `TestPoolProvider_BlanketByTelegramIDDoesNotRevokePool`: blanket
  revoke an account's Telegram id; the pool token still authenticates; a job
  token derived for that account is refused. Mutation: pool provider passing a
  non-zero Telegram id to `IsRevoked`.
- [ ] T4. `TestPoolProvider_RejectsAccountShapedClaims`: table over
  `telegram_id`, `tg_username`, `job_id`, `job_attempt`, `conv_id`,
  `job_tools`, missing jti, `sub=tg:...`, bad name, `aud=agent`; plus the
  reverse: `aud=agent-pool` refused by the `agent` and `agent-job` providers.
  Mutation: remove any single shape check.
- [ ] T5. `TestPoolCredential_ClaimOnly`: iterate every route registered by
  `Server.Register` (captured through a recording registrar, so a new route is
  covered automatically); each returns 403 for a pool identity except
  `POST /jobs/claim`. Mutation: drop `requireNotPool` from any route.
- [ ] T6. `TestHandleClaimJobs_Pool_MintsJobTokenFromJobUser`: job token
  `sub=tg:<job user>`, `TelegramID` of the job user, `jti`/`orig_iat` of the
  pool, and the job-token provider resolves to the job's `UserID`. Mutation:
  copy Subject/TelegramID from the parent.
- [ ] T7. `TestHandleClaimJobs_Pool_RoundRobin`: three managed accounts with
  two due jobs each, `limit=3` -> one job per account; `limit=10` -> still
  three. Mutation: claim `limit` jobs for the first account.
- [ ] T8. `TestHandleClaimJobs_Pool_InflightCap`: account at the cap is skipped.
  Mutation: drop the processing-count filter.
- [ ] T9. `TestHandleClaimJobs_Pool_RendersBeforeClaim`: an account whose
  assistant is disabled in the registry is skipped and its jobs stay pending
  (status and attempts unchanged); other accounts are served. Mutation: claim
  before rendering.
- [ ] T10. `TestHandleClaimJobs_Pool_NoJobSigner503`: 503 and no job changes
  status. Mutation: remove the signer check.
- [ ] T11. `TestClaimAudit_UsesJobUser`: the audit row has the job's user id
  and message `pool:<name>`; the account branch still audits under its own
  user with an empty message. Mutation: audit under `id.UserID`.
- [ ] T12. `TestRuntimeSwitch_FencesInflightJob`: own claims a job, the admin
  route switches the account to managed (install revision bumps), the old
  attempt's `propose_reply`/`complete` are refused by the fence, the job is
  requeued by `RequeueStaleAgentJobs`, and the pool reclaims it with
  `runtime = 'managed'`. Mutation: remove the bump in `RuntimeChange.Apply`.
- [ ] T13. `TestPoolToken_Mint` (handler): claims, TTL default/clamp, huge
  `ttl_hours` does not overflow, 401/403/400, unknown field 400, log line has
  no token. Mutation: compute TTL as `Duration(hours)*Hour` before clamping.
- [ ] T14. `TestServer_PoolFlagOff`: with `MANAGED_RUNTIME_ENABLED=false` the
  mint route is 404 and a pool token is 401 on `/api/agent/v1/jobs/claim`.
- [ ] T15. Worker: `TestClaudeInvoker_PoolMode_NoFallback`,
  `TestFinishRun_PoolMode_UsesJobToken` (both runners, asserting the
  Authorization header on `GET /jobs/{id}` and `POST /jobs/{id}/cost`), and
  `TestClaudeInvoker_OwnMode_Unchanged`. Mutation: fall back to `APIToken`.
- [ ] T16. `TestHandleClaimJobs_OwnPathUnchanged`: account-token claim for an
  own account returns the same envelope fields and job-token claims as before.

## Rollback

All new behaviour is behind `MANAGED_RUNTIME_ENABLED` (server) and
`AGENT_POOL_MODE` (worker), both off in every environment today. Fastest first:
set the account back to `runtime: own` (the fence does the rest); scale the
pool worker to 0; revoke the pool `jti` via `revoke_worker_token` (15 s);
turn `MANAGED_RUNTIME_ENABLED` off (pool tokens get 401, the mint route
disappears). For a code-level rollback, revert the merge commit: the
`agent_jobs.runtime` column is additive and nullable and can stay in place;
older code ignores it. The only change active with the flag off is the runtime
predicate (always true for own/profile-less accounts) and the revision bump on
an actual runtime change; reverting restores the previous queries exactly.
