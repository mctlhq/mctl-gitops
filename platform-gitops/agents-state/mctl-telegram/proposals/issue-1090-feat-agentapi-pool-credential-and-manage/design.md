# Design: issue-1090-feat-agentapi-pool-credential-and-manage

## Current state

What is already in the tree (read in the clone at `b1d5383`):

- **Slice 1 (#1089) landed.** `internal/db/agent_schema.go` adds
  `agent_profiles.runtime TEXT NOT NULL DEFAULT 'own'`,
  `managed_consent_version`, `managed_consent_at`, and an unused
  `budget_paused_until`. Constants `db.RuntimeOwn`, `db.RuntimeManaged`,
  `db.ManagedConsentCurrent = "managed-data-flow/v1"` live in
  `internal/db/managed_runtime.go`; `AgentProfile.NeedsManagedReconsent()` in
  `internal/db/agent_domain.go`. `internal/config/config.go` parses
  `MANAGED_RUNTIME_ENABLED` (default false) and `MANAGED_RUNTIME_MAX_ACCOUNTS`.
  `internal/assistantinstall/runtime.go` (`ManagedRuntime.DecideRuntime`,
  `RuntimeChange.Apply`) gates the switch on flag, consent and quota.
- **There is no `agent_jobs.runtime` column** and no runtime predicate in either
  claim query.
- **Credentials.** `internal/auth/localjwt/issuer.go`: `Claims` carries `jti`,
  `orig_iat`, `job_id`, `job_attempt`, `conv_id`, `job_tools`.
  `Provider.Authenticate` verifies, checks audience, consults
  `RevocationCache.IsRevoked(jti, telegramID, originAnchor(c))` when
  `needsRevocationCheck(c)` (true for any `jti`, worker audiences, or
  `derivedAudiences = {"bridge","agent","agent-job"}`), then always calls
  `Store.EnsureUserByTelegramID` (which rejects `tgID <= 0`).
  `internal/auth/localjwt/revocation.go`: `RevocationCache` holds a jti set and a
  blanket map keyed by Telegram id; `Store.RevokeWorkerTokensForTelegramID`
  refuses `telegramID <= 0`, so a Telegram id of 0 can never be blanket-revoked.
- **Identity.** `internal/auth/identity.go` `auth.Identity` has `Jti`,
  `OriginalIssuedAt`, `JobID`, `JobAttempt`, `ConversationID`, `JobTools`; no
  pool field.
- **Wiring.** `cmd/server/main.go` (inside `if cfg.AgentEnabled`): mounts
  `POST /api/agent/token` (`agentapi.NewAgentTokenHandler`, admin `admin:users`),
  builds `agentProvider := selectAgentProvider(...)` (`aud=agent`, local-jwt or
  shared-hmac), chains `selectAgentJobProvider` (`aud=agent-job`, always
  localjwt with `PublicBaseURL` issuer) via `chainProvider`, wires
  `agentSrv.WithJobTokenSigner(localjwt.NewIssuer(OAUTH_JWT_SECRET, PublicBaseURL))`
  and mounts `/api/agent/v1` behind `auth.Middleware(agentProvider, ...)`.
- **Account token mint.** `internal/agentapi/tokenhandler.go`: 30 d default,
  90 d cap, computes `time.Duration(req.TTLHours) * time.Hour` (overflow-prone;
  `internal/workertoken/minter.go` `clampTTL` compares in hours instead). The
  account token carries no `jti`. `workertoken.LogMinted` is the log shape to
  mirror; `workertoken.generateJti` is unexported (128-bit, base64url).
- **Routes.** `internal/agentapi/server.go` `Register` wraps every route in
  `toolGate`: `GET /events` (legacy, calls `handleClaimJobs`),
  `GET /event/{eventID}`, `GET /conversations/{id}/context`,
  `GET /conversations/{id}/leads`, `GET /recruiters/{peer}`, `GET /leads/{id}`,
  `GET /policy`, `GET /jobs/{id}`, `POST /actions/propose_reply`, `POST /leads`,
  `POST /actions/request_owner_approval`, `POST /notify/summary`,
  `POST /autopilot/pause`, `POST /jobs/claim`, `POST /jobs/{id}/complete`,
  `POST /jobs/{id}/cost`. `toolGate` (`toolgate.go`) resolves the caller's tool
  set from `id.UserID` for non-job tokens; with `UserID=0` that would be wrong,
  so the pool guard must run before it.
- **Binding guards.** `internal/agentapi/binding.go`: `jobBound`,
  `enforceBinding`, `requireAccountToken` (refuses a job token on account-scoped
  routes), `denyBinding` audits via `s.audit(ctx, id.UserID, ...)`.
- **Audit.** `internal/agentapi/json.go` `audit` calls `Store.LogToolCall`;
  `audit_logs.user_id` is `REFERENCES users(id)` (`internal/db/db.go`), and
  `LogToolCall` inserts the user id as given, so a pool identity (`UserID=0`)
  cannot be audited there.
- **Claim handler.** `internal/agentapi/events.go` `handleClaimJobs`: requires an
  account token, renders `accountInstructions(r, id.UserID)` before claiming
  (503 on disabled/unknown/fork-not-runnable), `tools.ForJob` ->
  `tools.CanonicalNames`, long-polls `s.Queue.Claim(ctx, id.UserID, limit)`,
  builds `jobEnvelope` with `mintJobToken(id, j, jobTools)` and audits
  `get_events ok` under `id.UserID`. `mintJobToken` copies Subject/TelegramID
  from the parent and returns "" when `parent.TelegramID == 0` or no signer.
- **Queue.** `internal/agent/queue/queue.go` `Queue.Claim(ctx, userID, limit)`
  -> `Store.ClaimAgentJobs(ctx, replicaID, userID, limit)`.
- **Claim SQL.** `internal/db/agent_jobs.go` `ClaimAgentJobs` (UPDATE ... WHERE
  id IN (SELECT ... WHERE j.status=$4 AND j.next_run_at<=$3 AND j.user_id=$6 AND
  NOT EXISTS(...) ... FOR UPDATE SKIP LOCKED)), stamps `install_revision` from
  the profile. When `s.turnCfg != nil` it delegates to
  `internal/db/agent_turn_claim.go` `claimCoalesced`, whose candidate SELECT
  (`loadClaimCandidates`) filters `j.user_id = $3` and whose per-head UPDATE
  stamps `install_revision`.
- **Fence.** `internal/agentapi/actions.go` compares `job.InstallRevision` with
  the profile's. `assistantinstall.Service.Commit` sets
  `BumpInstallRevision: true`, but the admin route
  `internal/agentapi/profilehandler.go` (`PUT /api/admin/agent/profile`) applies
  a runtime change through `RuntimeChange.Apply` without bumping the revision,
  so a runtime switch through that route would not fence the in-flight attempt.
- **Worker.** `internal/agentworker/claudeinvoker.go` `mcpToken` falls back to
  `c.APIToken` when `job.JobToken == ""`; `ClaudeInvoker.Run` and
  `OpenAIRunner.Run` call `finishRun` with a client on the account token
  (`APIToken`), which issues `GetJobStatus` and `ReportJobCost`.
  `OpenAIRunner.Run` already refuses a job without a job token
  (`errNoJobToken`). `cmd/agent-worker/main.go` reads `AGENT_API_TOKEN`,
  `AGENT_RUNNER`; there is no `AGENT_POOL_MODE`. The worker loop
  (`worker.go`) only uses the account token for `PollEvents`.
- `Store.TelegramIDByUserID` (`internal/db/store.go`) reads
  `users.telegram_login_id`, found=false for NULL/0.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: `AUTH_MODE:
  local-jwt`, `AGENT_ENABLED: "true"`, `AGENT_TURN_QUIET: "3s"` (so production
  claims run through `claimCoalesced`), no `MANAGED_RUNTIME_ENABLED` (flag off by
  default).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: `AUTH_MODE:
  local-jwt`, `AGENT_ENABLED: "true"`, `AGENT_TURN_QUIET: "3s"`, no
  `MANAGED_RUNTIME_ENABLED`.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`: the own
  worker, `AGENT_API_TOKEN` from
  `secret/data/platform/labs/agent-worker-preview/api` (aud=agent account
  token), no `AGENT_POOL_MODE`, no `AGENT_RUNNER` (defaults to `claude`).
- No `agent-worker-managed-preview` component exists in `services/labs` yet
  (expected; it is mctl-gitops#2345).
- mctl MCP tools were not used; gitops files were sufficient for the flags this
  slice depends on. Live pod env was not observed.

## Proposed solution

### 1. Pool credential (`internal/auth/localjwt/pool.go`, `internal/auth/identity.go`)

- `auth.Identity` gains `Pool string` — the pool name, set only by
  `PoolProvider`. Helper `func (i *Identity) IsPool() bool { return i != nil && i.Pool != "" }`.
- `const PoolAudience = "agent-pool"`, `const PoolSubjectPrefix = "pool:"`, and
  `var poolNameRE = regexp.MustCompile("^[a-z0-9][a-z0-9-]{0,62}$")` exported as
  `ValidPoolName(string) bool` so the mint handler and the verifier share one
  rule.
- `derivedAudiences` becomes `{"bridge", "agent", "agent-job", "agent-pool"}` so
  `needsRevocationCheck` is true for a pool token even without a jti (which the
  provider rejects anyway — belt and braces, and the shared helper stays
  truthful).
- `type PoolProvider struct { Secret []byte; ExpectedIssuer string; RevocationCache *RevocationCache }`
  with `NewPoolProvider(cfg PoolProviderConfig) (*PoolProvider, error)` that
  refuses an empty secret, empty issuer or nil `RevocationCache` (a pool with no
  revocation path must not exist).
- `Authenticate(r)`: Bearer header only (no cookie fallback — the pool is a
  headless credential; the `mctl_connect_token` cookie path is for browsers);
  `VerifyWithClaims`; `CheckAudience(c.Audience, "agent-pool", true)`; then
  `checkPoolShape(c)` rejecting `TelegramID != 0`, `TelegramUsername != ""`,
  `JobID != 0`, `JobAttempt != 0`, `ConversationID != 0`, `len(JobTools) > 0`,
  `DeviceID`/`ClientID`/`Profile` set, `Jti == ""`, subject without the
  `pool:` prefix, invalid name; then `RevocationCache.IsRevoked(c.Jti, 0, originAnchor(c))`
  fail-closed. Returns `&auth.Identity{UserID: 0, Subject: c.Subject, Pool: name,
  Provider: "tg-mcp-pool", Scopes: nil, Jti: c.Jti, OriginalIssuedAt: c.OriginalIssuedAt}`.
  It never calls `EnsureUserByTelegramID`. Errors are wrapped in
  `auth.AttributedError` like `Provider`.
- Shape confusion the other way is already covered: `Provider` with
  `ExpectedAudience: "agent"` or `"agent-job"` and `AudienceRequired: true`
  rejects `aud=agent-pool`. A test pins it.

### 2. Mint route (`internal/agentapi/pooltokenhandler.go`)

- `NewPoolTokenHandler(secret []byte, issuer string) http.HandlerFunc`, same
  structure as `NewAgentTokenHandler`: 401 without identity, 403 without
  `admin:users`, `decodeStrict` into `{pool_name string, ttl_hours int}`, 400 on
  invalid name. TTL: reuse `defaultAgentTokenTTL` / `maxAgentTokenTTL`, clamped
  in hours (`if hours <= 0 -> 30d; if hours > 2160 -> 90d`) to avoid the
  `time.Duration` overflow `clampTTL` documents. `jti` from a new exported
  `workertoken.GenerateJti()` (rename/wrap of `generateJti`, no behaviour change)
  so one generator exists. Claims: `Subject: "pool:"+name`, `Audience:
  {"agent-pool"}`, `Jti`, `OriginalIssuedAt: now.Unix()`.
- Log line `slog.Info("pool token minted", "admin_user_id", ..., "via",
  "http", "pool", name, "ttl", ttl, "expires_at", ..., "audience_marker",
  "agent-pool", "jti", jti)` — the same key set as `workertoken.LogMinted` minus
  the Telegram fields. No token value is ever logged. Response
  `{pool_token, expires_at, jti}` (jti returned so the operator can record it
  for `revoke_worker_token`).
- The issuer is always `strings.TrimRight(cfg.PublicBaseURL, "/")` and the
  secret `OAUTH_JWT_SECRET` — the same pair as the job-token signer — regardless
  of `AUTH_MODE`, so the pool provider is mode-independent like
  `selectAgentJobProvider`.

### 3. Server wiring (`cmd/server/main.go`)

Inside `if cfg.AgentEnabled`, only `if cfg.ManagedRuntimeEnabled && cfg.OAUTHJWTSecret != ""`:
- mount `POST /api/agent/pool-token` behind
  `auth.Middleware(provider, true, m, resourceMeta)` (the regular MCP provider,
  same as `/api/agent/token`);
- `selectAgentPoolProvider(cfg, workerTokenRevocationCache)` and append it to
  the chain *after* the agent and job providers:
  `agentProvider = chainProvider{agentProvider, jobProvider, poolProvider}`
  (build the slice conditionally so the nil-job-provider case still works);
- `agentSrv.WithManagedClaims(ManagedClaimConfig{MaxInflightPerAccount: cfg.ManagedMaxInflightPerAccount, Revocations: workerTokenRevocationCache})`.
When the flag is off none of this is constructed: a pool token gets 401 and the
mint route 404. Log `managed runtime pool credential enabled` once.
`internal/config/config.go` gains `ManagedMaxInflightPerAccount`
(`MANAGED_MAX_INFLIGHT_PER_ACCOUNT`, default 1, must be >= 1).

### 4. Claim-only guard (`internal/agentapi/binding.go`, `server.go`)

- `func (s *Server) requireNotPool(route string, h http.HandlerFunc) http.HandlerFunc`:
  if `auth.From(ctx).IsPool()`, write 403 `{"error":"pool_credential_claim_only"}`,
  emit `slog.Warn("agentapi pool credential refused", "pool", id.Pool, "route", route, "jti", id.Jti)`,
  increment `CountPolicyDenial("pool_claim_only", metrics.PolicySurfaceToolGate)`
  (or a new surface label), and — when the route has a `{id}` job parameter that
  resolves via a new `Store.AgentJobOwner(ctx, jobID)` to a managed account —
  also `s.audit(ctx, ownerUserID, routeTool, "denied", "pool:"+id.Pool+" claim-only")`.
  No audit row is attempted with `UserID=0` (FK).
- `Register` applies the guard to every route **outside** `toolGate` (the gate
  would otherwise resolve a tool set for user 0): `get := func(p, h) {
  mux.Get(p, s.requireNotPool("GET "+p, s.toolGate("GET "+p, h))) }`, and the
  single exception is registered explicitly:
  `mux.Post("/jobs/claim", s.toolGate("POST /jobs/claim", s.handleClaimJobs))`.
  `GET /events` (legacy) stays pool-refused.
- Inside `handleClaimJobs` the existing `requireAccountToken` still refuses job
  tokens; a pool identity branches to `s.handlePoolClaim(w, r, id, limit)` after
  limit parsing.

### 5. Runtime predicate and claim stamp (`internal/db/agent_jobs.go`, `agent_turn_claim.go`, `agent_schema.go`)

- Schema: `addColumnIfMissing(ctx, dbConn, pg, "agent_jobs", "runtime", "TEXT", "TEXT")`
  (nullable: NULL means "never claimed since the column existed").
  `AgentJob.Runtime string`, added to `agentJobCols`, both `RETURNING` lists,
  `GetAgentJob` and `scanAgentJobs` (`sql.NullString`).
- Signature change: `ClaimAgentJobs(ctx, replicaID string, userID int64, runtime string, limit int)`
  and `claimCoalesced(ctx, replicaID, userID, runtime, limit)`; `runtime` must be
  `RuntimeOwn` or `RuntimeManaged`, else error. `Queue.Claim(ctx, userID,
  runtime, limit)` passes it through; the account branch passes `db.RuntimeOwn`.
- Plain query: inner SELECT gains
  `AND COALESCE((SELECT ap.runtime FROM agent_profiles ap WHERE ap.user_id = j.user_id), 'own') = $7`;
  outer UPDATE sets `runtime = $7`.
- Coalesced query: the candidate SELECT gains the same predicate (`$6`), and the
  per-head UPDATE sets `runtime = $7`. `readyTurn` needs no predicate (followers
  are the same user and conversation and are coalesced, not claimed).
- Defining the predicate text once as a Go constant
  (`claimRuntimePredicate = "COALESCE((SELECT ap.runtime FROM agent_profiles ap WHERE ap.user_id = j.user_id), 'own') = "`)
  makes the mutation test meaningful: the test drives both paths through real
  SQL, not through the constant.
- `ListManagedClaimCandidates(ctx, now time.Time, maxInflight, limit int) ([]ManagedClaimCandidate, error)`
  in a new `internal/db/agent_managed_claim.go`:
  ```sql
  SELECT ap.user_id, u.telegram_login_id, MIN(j.next_run_at) AS oldest
    FROM agent_profiles ap
    JOIN users u       ON u.id = ap.user_id
    JOIN agent_jobs j  ON j.user_id = ap.user_id AND j.status = 'pending' AND j.next_run_at <= $1
   WHERE ap.runtime = 'managed'
     AND ap.managed_consent_version = $2               -- ManagedConsentCurrent
     AND u.telegram_login_id IS NOT NULL AND u.telegram_login_id <> 0
     AND (SELECT COUNT(*) FROM agent_jobs p
           WHERE p.user_id = ap.user_id AND p.status = 'processing') < $3
     -- slice 4 (#1092): budget filter goes here
   GROUP BY ap.user_id, u.telegram_login_id
   ORDER BY oldest, ap.user_id
   LIMIT $4
  ```
  Read-only, no locks: the claim itself (with SKIP LOCKED and the runtime
  predicate) remains the only authority, so a stale candidate only costs an
  empty claim.

### 6. Pool claim branch (`internal/agentapi/events.go`)

`handlePoolClaim(w, r, id, limit)`:
1. `if s.jobTokenSigner == nil` -> 503 `"job tokens not configured"`, claim
   nothing.
2. Long-poll loop with the same `longPollTimeout` / `eventsPollInterval` as the
   account branch. Each iteration: `cands := ListManagedClaimCandidates(ctx,
   now, s.managed.MaxInflightPerAccount, limit*4)` (over-fetch so skipped
   accounts do not starve the response).
3. Round robin: for each candidate in order, until `len(out) == limit`:
   - skip when a new `RevocationCache.IsBlanketRevoked(ctx, c.TelegramID, poolOrigin)`
     (the blanket half of `IsRevoked`, same refresh and fail-closed rules, no
     jti lookup) reports a blanket revocation at or after the pool's `orig_iat`
     — the job token would be dead on arrival (see Open questions); a cache
     error skips the account too;
   - `accountInstructions(r, c.UserID)` and `tools.ForJob`; any error -> log
     with `user_id` (no content), skip, jobs stay pending;
   - `s.Queue.Claim(ctx, c.UserID, db.RuntimeManaged, 1)`; zero jobs -> next;
   - `tok := s.mintJobTokenFor(id, j, jobTools)`; if `tok == ""` ->
     `Store.RetryAgentJob(ctx, j.ID, j.Attempts, "job token mint failed")`
     and skip (a pool-claimed job is never returned without a token);
   - append the envelope (same `jobEnvelope` fields as the account branch) and
     `s.audit(ctx, c.UserID, "get_events", "ok", "pool:"+id.Pool)`.
   One pass over candidates is one round; with limit > 1 the loop does further
   rounds only over accounts not yet served in this response, so it is one job
   per account per response by construction.
4. Return when `out` is non-empty, else wait for the next tick or the
   deadline, exactly as the account branch.

`mintJobToken` becomes a thin wrapper choosing subject source:
- account parent: unchanged (`parent.Subject`, `parent.TelegramID`,
  `parent.TelegramUsername`) — own path byte-for-byte;
- pool parent: `tg, ok, err := s.Store.TelegramIDByUserID(ctx, j.UserID)`;
  `!ok || err != nil` -> ""; claims `Subject: "tg:"+tg`, `TelegramID: tg`,
  `TelegramUsername: ""` (EnsureUserByTelegramID does not overwrite on empty),
  `Jti: parent.Jti`, `OriginalIssuedAt: parent.OriginalIssuedAt`, same TTL,
  job binding and `job_tools`. The job-token provider then resolves the user
  from that Telegram id, which is the job's user.

### 7. Runtime switch fence (`internal/assistantinstall/runtime.go`)

`RuntimeChange.Apply` sets `u.BumpInstallRevision = true` whenever
`c.Runtime != nil && c.From != c.To`. That covers the admin profile route
(which today does not bump) and is idempotent for the install service (which
already bumps). The existing fence in `actions.go` then refuses the old
attempt; `RequeueStaleAgentJobs` requeues after `AGENT_JOB_VISIBILITY`; the new
runtime's claim (the predicate reads the profile live) picks it up.

### 8. Worker (`internal/agentworker`, `cmd/agent-worker/main.go`)

- `AGENT_POOL_MODE` parsed with the existing `envBool`-style helper (strict
  true/false, error on garbage). Passed as `PoolMode bool` to both runners.
- `ClaudeInvoker.mcpToken`: in pool mode return `job.JobToken` only;
  `ClaudeInvoker.Run` returns `errNoJobToken` (move the sentinel to a shared
  file) before spawning `claude` when the token is empty.
- `finishRun` callers: in pool mode build the `finishRun` client with
  `job.JobToken` (Claude: `NewClient(c.APIBaseURL, job.JobToken, nil)`; OpenAI:
  `workerAPI = api` when `r.PoolMode`). Outside pool mode both remain on
  `APIToken`, unchanged.
- No change to `PollEvents` — the pool token is used for exactly the one route
  it may call.

## Alternatives

- **Reuse `localjwt.Provider` for the pool with a "skip ensure-user" flag.**
  Smaller diff, but every future change to `Provider` (cookie fallback,
  EnsureUser, attribution) silently applies to the widest credential in the
  system. A separate type with its own shape check keeps the pool's rules in one
  short, testable function. Dropped.
- **Enforce own/managed separation in the handler** (filter candidate users in
  Go, keep SQL as is). The ADR makes SQL the invariant; a handler filter is
  bypassed by any future caller of `Queue.Claim`, and the own path would have no
  protection against claiming a managed account's job. Dropped.
- **One cross-account claim query** (`ClaimManagedJobs` claiming across users in
  one UPDATE). Fewer round trips, but it cannot render instructions per account
  before claiming, makes the in-flight cap and round robin harder to express,
  and duplicates the coalescer. Per-account `Claim(..., 1)` reuses both existing
  queries unchanged apart from the predicate. Dropped.
- **Wrap the guard inside `toolGate`.** Would couple two policies and the gate
  resolves a tool set from `UserID` before it could refuse; a separate outer
  wrapper is clearer and is what the route-table test asserts.

## Platform impact

- **Migrations:** one additive nullable column `agent_jobs.runtime` via
  `addColumnIfMissing` (both dialects). No backfill; NULL for historical rows.
  The ledger slice copies it from the claim-time value.
- **Backward compatibility:** with `MANAGED_RUNTIME_ENABLED` off (all current
  environments per gitops) the only behavioural changes are (a) the runtime
  predicate, which for an `own` or profile-less account is always true, and (b)
  the runtime-switch revision bump on the admin route, which can only fire when
  the runtime actually changes (impossible to `managed` with the flag off). The
  own worker's claim, job token, audit row and worker calls are unchanged; a
  regression test compares the own-path envelope and token claims before/after.
- **Resource impact:** the predicate adds a correlated subquery on
  `agent_profiles(user_id)` (primary key/unique) per candidate row — negligible.
  The candidate query runs once per poll tick of the single pool worker
  (`eventsPollInterval`), grouped over pending jobs; with
  `MANAGED_RUNTIME_MAX_ACCOUNTS=1` at first it is tiny. `idx_agent_jobs_claim
  (status, next_run_at)` serves the join.
- **Risks and mitigations:**
  - Pool token leak -> holder can claim managed jobs only; it receives job tokens
    bounded by the job binding and tool gate. Mitigations: claim-only guard,
    `jti` revocation propagating to derived job tokens (tested), 30 d TTL,
    in-cluster URL, flag.
  - Job token expiry at deadline in pool mode can drop a late cost report (401).
    Accepted for this slice and recorded for #1092.
  - Blanket account revocation makes future pool-derived tokens for that
    account dead on arrival; mitigated by skipping such accounts in the pool
    branch.
  - Signature change of `ClaimAgentJobs`/`Queue.Claim` touches every test
    caller; mechanical, compiler-enforced.
  - Audit rows for pool refusals cannot use `UserID=0`; mitigated by slog +
    metric, plus the job owner's row when resolvable.
