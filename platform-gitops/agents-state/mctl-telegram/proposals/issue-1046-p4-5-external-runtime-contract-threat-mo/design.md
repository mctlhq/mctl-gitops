# Design: issue-1046-p4-5-external-runtime-contract-threat-mo

## Current state

**The job API.** `internal/agentapi` is the only surface agent code uses to
reach mctl-telegram data or Telegram sends (package doc, `server.go`).
`Server.Register` binds 16 routes under `/api/agent/v1`. Each is wrapped in
`toolGate`:
- `GET /events` (legacy, carries `Deprecation`/`Sunset` headers)
- `GET /event/{eventID}`
- `GET /conversations/{id}/context`
- `GET /conversations/{id}/leads`
- `GET /recruiters/{peer}`
- `GET /leads/{id}`
- `GET /policy`
- `GET /jobs/{id}`
- `POST /actions/propose_reply`
- `POST /leads`
- `POST /actions/request_owner_approval`
- `POST /notify/summary`
- `POST /autopilot/pause`
- `POST /jobs/claim`
- `POST /jobs/{id}/complete`
- `POST /jobs/{id}/cost`

The mount is in `cmd/server/main.go`, around line 847:
`mux.Mount("/api/agent/v1", auth.Middleware(agentProvider, true, ...))`. Here
`agentProvider` is `chainProvider{selectAgentProvider(...), selectAgentJobProvider(...)}`.

**Credentials today.**
- Account token. `POST /api/agent/token` (`internal/agentapi/tokenhandler.go`,
  `NewAgentTokenHandler`) is admin-only (`admin:users`) and mints `aud=agent`,
  `sub=tg:<id>`. TTL is 30 days by default and clamped to 90 days. **No `jti`
  is set**, so the only way to revoke it is a blanket revocation by Telegram id
  (`derivedAudiences` in `internal/auth/localjwt/issuer.go` contains `agent`).
  `jobBound(id)` is false for it, so `enforceBinding`
  (`internal/agentapi/binding.go`) is a no-op. The token can claim, read any
  conversation's context, leads and events of the account, and call every
  per-job route for any job of the account.
- Job token. `mintJobToken` (`internal/agentapi/events.go`) mints
  `aud=agent-job` at claim. It carries `JobID`, `JobAttempt`, `ConversationID`
  and signed `JobTools`, and inherits the parent's `jti`/`orig_iat`. Its TTL
  ends at `ClaimedAt + jobVisibility`; `AGENT_JOB_VISIBILITY` defaults to 5 min
  (`internal/config/config.go`). Every reading or writing route checks it:
  - `enforceBinding` on propose, save_lead, approval/summary/pause, context,
    get_lead, get_agent_job, complete and cost;
  - a job/event check in `handleGetEvent`;
  - a peer check in `handleRecruiterProfile`;
  - a lead-conversation check in `handleGetLead`;
  - `requireAccountToken` refuses it on `POST /jobs/claim`.

  `toolGate` (`internal/agentapi/toolgate.go`) takes the tool set from the
  signed claim and never from the request.
- If no signer is configured, `mintJobToken` returns `""`. The claim response
  then has no `job_token` and the worker falls back to its account token
  (`ClaudeInvoker` in `internal/agentworker/claudeinvoker.go:143`). The OpenAI
  runner refuses instead (`errNoJobToken`, `internal/agentworker/openairunner.go`).
- The revocation cache (`internal/auth/localjwt/revocation.go`) checks a `jti`
  denylist and blanket-by-telegram-id entries. Its staleness is bounded by
  `MaxRevocationCacheTTL` = 15 s. `needsRevocationCheck` runs for any token
  with a `jti`, and for `jti`-less tokens of worker or derived audiences.

**Errors.** `writeJSONError` (`internal/agentapi/json.go`) writes
`{"error": "<free text>"}`. Policy refusals carry `policy.DenyCode` values,
for example `tool_not_allowed`, `install_changed`, `source_message_superseded`
and `intent_never` (`internal/agent/policy/policy.go`). Everything else is
prose such as "job is no longer claimed under that attempt" or "credential is
bound to another conversation".

**What a worker can read.** Through these sources a worker sees Telegram data,
owner data and instructions:
- event bodies and sender metadata (`GET /event/{id}`);
- conversation history (`/conversations/{id}/context`);
- the owner profile view from `OwnerProfileProvider.PublicProfile`, which
  strips the restricted section and the `never` fields, and reveals
  `after_owner_engaged` fields only once the owner has engaged
  (`GET /recruiters/{peer}`);
- leads (`/leads/{id}`, `/conversations/{id}/leads`);
- the policy (`/policy`);
- the claim envelope (`jobEnvelope` in `events.go`), which carries the rendered
  `instructions` (catalog prompt plus owner notes), the tool aliases and the
  `install_revision`.

The worker never sees Telegram session material: sends happen server-side
after policy and the send gate (ADR 0002).

**Docs.** The job loop and the tools are described in `docs/agent-worker.md`
(written for the first-party worker). `docs/assistants/spec.md`, tier table
row "T4 Own runtime", says "account-scoped token; policy enforced
server-side". No threat model exists. `docs/contracts/` holds two mctl-api
contracts with the same structure the new doc will follow.
`docs/compatibility_test.go` shows the existing pattern of tests that keep
docs in sync.

**C1 harness.** `internal/agenteval` contains:
- the suite loader (`suite.go`);
- `Prepare`/`Target` (`target.go`);
- `Task`, a fake per-fixture agent API (`fake.go`) that enforces
  `tools.Endpoints`, records binding violations in `boundBody` and runs
  propose through the real policy engine as a guarded dry run;
- `Score` (`score.go`).

`internal/agentworker/eval_test.go` (`TestC1ObserveEval`) drives it. For each
fixture it creates `httptest.NewServer(task)` and a `JobEnvelope` by hand, and
calls `ClaudeInvoker.Run` or `OpenAIRunner.Run` directly in-process. The fake
does not serve `POST /jobs/claim`. It accepts one static token
(`"c1-eval-token"`) as both the worker credential and the job token. So it
cannot test an arbitrary binary end to end, and it cannot tell "used the
claim credential on a per-job route" apart from correct use.
`AGENT_EVAL_WORKER_BIN` only swaps the stdio MCP server binary. The acceptance
bar is in `docs/agent-worker.md` ("Testing") and ADR 0008: classification at
least 29/32, 32/32 terminal, 0 leaks, 0 binding violations, 0 wrong auto-sends.

**Relationship to ADR 0008.** ADR 0008 (Proposed; #1090 not merged — no
`agent-pool`/`requireNotPool` symbols exist in the clone) plans a claim-only
`aud=agent-pool` credential with a `requireNotPool` guard. It cites #1046 as
its foundation. The claim-only guard below is designed to be the one guard
both credentials use.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`: shows
  `replicaCount: 0`, image tag `main-33aeab7`, and
  `AGENT_API_BASE_URL: http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1`
  (in-cluster). `AGENT_API_TOKEN` comes from the Vault ExternalSecret
  `secret/data/platform/labs/agent-worker-preview/api`; the comment says it is
  the `aud=agent` worker credential. This is the only deployed consumer of
  the account token found.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` and
  `services/labs/mctl-telegram/values.yaml` both have `AUTH_MODE: local-jwt`,
  `AGENT_ENABLED: "true"` and `AGENT_KILL_SWITCH: "false"`. Neither file sets
  `AGENT_JOB_VISIBILITY` (grep found nothing), so the code default of 5 min
  presumably applies. That is an inference from the absence of the key, not
  an observation of the running pod.
- `services/admins/mctl-agents-worker/values.yaml` matched a grep for
  `agent-worker`. It belongs to a different product (mctl-agents) and was not
  inspected further.
- The mctl MCP tools were not called in this run. Live pod env and replica
  state of the preview services were therefore not observed (see Open
  questions in requirements.md; this does not affect the design, which
  changes code and docs only).

## Proposed solution

Four deliverables in the issue's order. Each builds on the previous one.

### 1. Threat model: `docs/agent-runtime/threat-model.md`

A STRIDE-style document with these fixed sections, each threat tied to its
enforcing code:

- **Invariant**, quoted from the issue: claim -> external model -> propose ->
  MCTL policy -> MCTL send. The runtime holds no Telegram credential.
- **Assets:**
  - Telegram content (events, context, attachments metadata);
  - the owner profile view;
  - owner notes inside `instructions`;
  - leads and records;
  - the ability to cause a send;
  - runtime and job credentials;
  - the account's budget and cost ledger;
  - audit integrity (ADR 0003).
- **Actors:**
  - the external runtime operator, who is honest but may be careless;
  - a compromised runtime host;
  - the model, which may be prompt-injected through inbound Telegram text;
  - a network attacker;
  - another account's runtime.
- **Trust boundaries:** MCTL server | runtime process | model provider. The
  runtime and the provider are outside MCTL's control. Everything the API
  returns must be assumed to reach the provider.
- **Read exposure table.** One row per read route: what the route returns,
  which credential reaches it, the binding check, and what is stripped (for
  example `PublicProfile` stripping `never` and restricted fields).
- **Threats and mitigations**, at minimum:
  - T1 credential theft:
    - runtime token: claim-only, 7-day default, `jti`-revocable;
    - job token: about 5 min, one job/attempt/conversation;
  - T2 replay:
    - a job token past its attempt is refused by the attempt fence
      (`CompleteAgentJob`) and by the `install_revision` fence
      (`DenyInstallChanged`);
    - propose idempotency;
    - no TTL extension;
  - T3 cross-job/cross-account access: `enforceBinding`, the per-route
    checks, user scoping in every store query;
  - T4 tool widening: signed `job_tools`, `toolGate`;
  - T5 policy bypass: there is no route that sends; propose goes through
    `policy.Evaluate` and the send gate;
  - T6 prompt injection causing disclosure: `MatchProtected` and
    `intent_never` denials, owner approval in guarded mode;
  - T7 runtime claiming and never completing: the visibility sweeper,
    unclaimed routing to the owner;
  - T8 cost misreporting: affects only the reporter's own account in T4; the
    managed ledger is server-authoritative per ADR 0008;
  - T9 DoS: 1 MiB body cap (`maxRequestBodyBytes`), long-poll bound,
    claim limit at most 10;
  - T10 credential confusion: distinct audiences, the job provider requires
    `aud=agent-job`.
- **Residual risks:**
  - bearer tokens are not sender-constrained;
  - owner notes and the engaged profile view reach a provider MCTL does not
    choose;
  - existing account tokens keep their wide reach until the follow-up.

  Each has an owner and a revisit trigger.

### 2. Contract: `docs/contracts/agent-job-api.md`, plus stable error codes

- A versioned document, "agent job API v1", in the same layout as
  `docs/contracts/mctl-api-work-context.md`:
  - authentication and the credential matrix (runtime/job/account x route);
  - the job lifecycle: claim -> read -> propose/request approval/summary ->
    complete, plus job status;
  - the claim envelope fields (`jobEnvelope`);
  - per-route schemas;
  - the binding rules;
  - deadlines (`deadline` is advisory, the sweeper enforces);
  - idempotency and fencing (attempt, `install_revision`);
  - deprecations (`GET /events`, sunset 2026-12-31);
  - the error code table.
- **Error codes.** Add `writeAPIError(w, status, code, msg)` in
  `internal/agentapi/json.go`. It writes `{"error": msg, "code": code}`.
  `code` is a closed enum declared in a new `internal/agentapi/codes.go`:
  - `unauthenticated`, `invalid_request`, `not_found`;
  - `binding_mismatch` (from `denyBinding`), `credential_claim_only`,
    `account_route_job_credential` (from `requireAccountToken`);
  - `attempt_fenced` and `install_changed` (the 409s in `events.go` and
    `actions.go`);
  - `tool_not_allowed`, `tool_set_unavailable`;
  - `assistant_unavailable` (the 503s for registry disabled, lifecycle
    unknown, forks off);
  - `job_token_unavailable`;
  - `policy_denied`, with `reason` set to the `policy.DenyCode`;
  - `internal`.

  Existing `writeJSONError` call sites move to `writeAPIError`. The `error`
  string stays byte-identical, so existing workers that match on it, and
  `toolGate`'s `error: tool_not_allowed`, keep working.
- **Doc sync test.** `docs/agent_job_api_test.go` (package `docs`, the same
  pattern as `docs/compatibility_test.go`) parses the route table and code
  table from the doc. An exported `agentapi.Routes()`, which returns what
  `Register` binds (refactor `Register` to iterate it), and
  `agentapi.ErrorCodes()` supply the other side. The test fails on any
  difference.
- Update `docs/assistants/spec.md` (T4 row) and `docs/agent-worker.md` to link
  to the contract and to state that external runtimes use a runtime token.

### 3. Scoped credentials: claim-only runtime token plus job tokens

Decision: **external runtimes get only an `agent-runtime` credential, which
can claim and do nothing else, and the per-job tokens the server mints at
claim.** They never get an account `agent` token.

- **Mint.** `POST /api/agent/runtime-token`. `NewRuntimeTokenHandler` lives in
  `internal/agentapi/tokenhandler.go`, beside `NewAgentTokenHandler`, and
  reuses its admin gate and strict decoder:
  - body `{telegram_id, ttl_hours}`;
  - `aud=agent-runtime`, `sub=tg:<id>`, `TelegramID`, a fresh `jti` (reuse
    `workertoken`'s `generateJti` by exporting it, or a local copy), and
    `orig_iat`;
  - TTL 7 days by default, 30 days maximum (clamped, as the existing handlers
    do);
  - logged as `agent runtime token minted` with the admin id, target id,
    `jti` and TTL, never the token.

  Mounted in `cmd/server/main.go` next to `/api/agent/token`.
- **Verify.** `selectAgentRuntimeProvider` in `cmd/server/main.go` builds a
  `localjwt.NewProvider` with `ExpectedAudience: "agent-runtime"`,
  `AudienceRequired: true`, the shared `RevocationCache`, and a new
  `ProviderConfig.ClaimOnly: true`. The provider sets a new
  `auth.Identity.ClaimOnly bool` on success. It is chained:
  `chainProvider{agentProvider, jobProvider, runtimeProvider}`. It is signed
  under this service's own issuer in every `AUTH_MODE`, as the job provider
  is. It is present only when `OAUTH_JWT_SECRET` is set; with no secret,
  neither mint nor verify exists. `agent-runtime` is added to
  `derivedAudiences` in `internal/auth/localjwt/issuer.go`.
- **Guard.** In `internal/agentapi/binding.go`, add
  `requireNotClaimOnly(w, r, id, tool) bool`. It returns 403 with code
  `credential_claim_only` and audits `denied`. It is applied centrally in
  `Register`'s `get`/`post` wrappers to every route except `POST /jobs/claim`,
  so a new route is covered by default. ADR 0008's pool provider sets the same
  `ClaimOnly` flag; `requireNotPool` then becomes this guard.
- **Claim.** In `handleClaimJobs`, for a `ClaimOnly` identity:
  - refuse with 503 `job_token_unavailable` before claiming if
    `jobTokenSigner == nil`;
  - if `mintJobToken` returns `""` for a claimed job (signing failure, or a
    TTL already elapsed), release the claim with the existing requeue path
    and omit the job, rather than handing out a job the worker cannot act on.

  `mintJobToken` already copies `parent.Jti` and `parent.OriginalIssuedAt`, so
  revoking the runtime `jti` kills derived job tokens within 15 s.
- **Account tokens.** `NewAgentTokenHandler` starts minting a `jti`. Existing
  tokens without one keep working, and blanket revocation still reaches them.
  This closes ADR 0008's "today's account token has no `jti` at all" gap.
  Reach is unchanged; restricting it is an open question and a follow-up.
- **First-party worker.** The tool calls already use the job token when one
  is present. `ClaudeInvoker`'s fallback to the account token
  (`claudeinvoker.go:143`) is never reached, because a claim-only claim never
  returns a job without a `job_token`. The post-run `finishRun`
  (`internal/agentworker/finishrun.go`: `GetJobStatus` and `ReportJobCost`)
  is different. Both runners give it a client built from the configured
  worker token: `ClaudeInvoker.Run` uses
  `NewClient(c.APIBaseURL, c.APIToken, nil)` at `claudeinvoker.go:270`, and
  `OpenAIRunner.Run` builds `workerAPI` from `r.APIToken` when it is set, at
  `openairunner.go:53-56`. With a claim-only credential those two calls
  would get 403. Change both runners to build the `finishRun` client from
  `job.JobToken` when it is present, and fall back to the worker token only
  without one. This is required for the first-party worker to pass its own
  conformance run, and ADR 0008 §2 requires it too.

### 4. Conformance harness

- **Claim-serving fake.** New `internal/agenteval/conformance.go`, type
  `Conformance`, an `http.Handler` that wraps a queue of `Task`s:
  - `POST /jobs/claim` accepts only the harness claim token. It returns the
    next fixture's `JobEnvelope`: job id, attempt 1, conversation 1, the
    `instructions` from `Target.Instructions`, `tools` from
    `Target.JobTools`, the deadline, and a **fresh random `job_token` per
    job**. When the queue is empty it returns `{"jobs": []}` after a short
    hold.
  - Every other route is dispatched by bearer token to the owning `Task`.
  - Recorded as a new violation class, `claim_token_on_job_route`: the claim
    token used on a non-claim route (answered 403 `credential_claim_only`, as
    production does).
  - Recorded as binding violations: an unknown token (401); a job token used
    with another job's id, attempt or conversation in the path or body. These
    extend `Task.boundBody` to path ids.
  - `GET /jobs/{id}` (job status) and `POST /jobs/{id}/cost` are routed to the
    Task, as before.

  The fake still never reaches a store, the executor or Telegram:
  `TestNoPathToEffects` is extended to cover `conformance.go`. `Score` gains
  the new violation class as a hard failure. `HarnessVersion` is bumped to
  `agenteval/2`, because a run that passed under v1 can now fail.
- **Runner.** New `cmd/agent-conformance/main.go`, a CLI and not only a test.
  An external author can `go install` it or use it from the worker image.
  - Flags or env:
    - `--suite hr-recruiter@0.1.0` (catalog plus `agenteval.LoadSuite`);
    - `--worker-cmd "<argv>"` (`AGENT_CONFORMANCE_WORKER_CMD`), *or*
      `--listen :8099` (`AGENT_CONFORMANCE_LISTEN`);
    - `--timeout` (`AGENT_CONFORMANCE_TIMEOUT`, default 32 x 3 min);
    - `--filter`;
    - `--report out.json`.
  - With `--worker-cmd`: start an `httptest`-like server on loopback, then
    exec the command with `AGENT_API_BASE_URL=<url>` and
    `AGENT_API_TOKEN=<claim token>`, the env names `cmd/agent-worker` reads.
    Inherit the rest of the environment (model credentials are the author's),
    and kill the command when every fixture is terminal or the timeout hits.
  - With `--listen`: print the base URL and claim token, and wait for the
    same condition.
  - Output: the `Score` report as JSON with `harness_version`,
    `suite_digest`, `definition_digest`, per-fixture outcomes (no model text,
    as `FixtureResult` already guarantees) and a pass/fail exit code.
- **C1 reuse.** `TestC1ObserveEval` keeps its in-process mode for runner
  development. A new opt-in `TestC1Conformance` (`AGENT_CONFORMANCE=1`)
  builds `cmd/agent-worker` and runs it through `Conformance` as a black box.
  This is the C1 harness "run against any worker binary". The acceptance bar
  is the suite threshold plus 0 claim-token-on-job-route.
- `Dockerfile.agent-worker` already ships the eval test binary. Add the
  `agent-conformance` binary so the run can be a one-shot Kubernetes Job.

## Alternatives

- **Give external runtimes the existing account token (status quo, T4 row in
  spec.md).** Dropped. A leaked 30 to 90 day token with no `jti` reads every
  conversation of the account and acts on any job. That contradicts
  "narrow, short-lived, job-bound", and job-level binding is entirely
  voluntary for the holder.
- **Job tokens only, delivered by push (server -> runtime webhook) with no
  standing runtime credential.** This is the narrowest option. It needs the
  server to call out to arbitrary user endpoints (SSRF and egress surface,
  `internal/netsafe` work), retries and reachability for workers behind NAT
  (the Mac mini). It also reverses today's pull model, which every worker and
  the C1 harness use. Dropped for now. The claim-only token keeps pull and
  holds no reading power on its own.
- **Restrict the existing `aud=agent` token to claim-only in place.** This is
  simpler, with one credential. But it breaks the deployed first-party
  worker, and any worker without a signer (the shared-hmac
  `parent.TelegramID == 0` case in `mintJobToken`), in one step. It also gives
  no way to tell an external runtime apart in audit. It is kept as the open
  follow-up once `Worker` uses job tokens everywhere.
- **Sender-constrained tokens (DPoP or mTLS) now.** Stronger against theft,
  but there is no client-side support in the worker or the runtimes and no
  ingress mTLS. Recorded as a residual risk instead.

## Platform impact

- **Migrations:** none. No schema change: revocation reuses
  `worker_token_revocations`, and jobs and audit are unchanged.
- **Backward compatibility:**
  - Account tokens keep their reach. Newly minted ones gain a `jti`, which is
    additive (`needsRevocationCheck` already handles `jti`).
  - Error bodies gain a `code` field. The `error` text is unchanged, so
    strict clients that reject unknown fields are the only risk. The worker
    client (`internal/agentworker/client.go`) decodes errors leniently; this
    is verified in task 3.
  - `HarnessVersion` bumps to `agenteval/2`, so stored P4.3 eval run bindings
    (`agenteval/binding.go`) under v1 stay valid as historical records, but a
    re-run is v2.
- **Deployed config:** none required. The runtime provider is enabled
  wherever `OAUTH_JWT_SECRET` is set, which is already true in local-jwt
  `labs/mctl-telegram{,-preview}`. No gitops change ships with this proposal.
  Minting a runtime token for a real account is an operator action after
  merge.
- **Resources:** negligible. One extra provider in the auth chain on agent
  routes, and one extra revocation lookup per runtime/job request (cached,
  15 s TTL).
- **Risks and mitigations:**
  - *A central guard misses a route.* Applying it in `Register`'s wrappers,
    plus a table test over `agentapi.Routes()`, makes "new route without the
    guard" impossible.
  - *A claim-only claim strands jobs when signing fails.* The job is requeued
    rather than returned. The sweeper is the backstop.
  - *Chain ordering lets a runtime token authenticate as an account token.*
    The audiences differ (`agent` vs `agent-runtime`) and each provider
    requires its own audience. A test asserts that a runtime token is rejected
    by `selectAgentProvider` and is `ClaimOnly` through the chain.
  - *Conflict with ADR 0008 (#1090), which edits the same files.* Land this
    first and have #1090 reuse `ClaimOnly` and `requireNotClaimOnly`, or
    rebase whichever lands second. Both designs agree on semantics.
