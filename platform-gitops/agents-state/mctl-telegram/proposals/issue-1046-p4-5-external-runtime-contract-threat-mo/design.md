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
`agent-pool` symbols exist in the clone) plans a claim-only `aud=agent-pool`
credential for the managed runtime. It cites #1046 as its foundation. This
proposal documents that plan as design intent and implements none of it.

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
    - the account-scoped `aud=agent` token: 30 to 90 day lifetime, no `jti`,
      reach as stated below, revoked only by blanket revocation by Telegram id;
    - the job token: about 5 min, one job/attempt/conversation;
  - T2 replay:
    - a job token past its attempt is refused by the attempt fence
      (`CompleteAgentJob`) and by the `install_revision` fence
      (`DenyInstallChanged`);
    - propose idempotency;
    - no TTL extension;
  - T3 cross-job/cross-account access: `enforceBinding`, the per-route
    checks, user scoping in every store query. State plainly that
    `enforceBinding` is a no-op for the account token, so job binding is
    voluntary for a holder of it;
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
    `aud=agent-job`;
  - T11 compromised worker host or model provider: everything the API returns
    reaches them; mitigations are the above plus the fact that no route sends
    and no Telegram session material is exposed.
- **Blast radius of the account-scoped token**, a dedicated section: what a
  thief can read and do for the token's whole lifetime.
- **Residual risks:**
  - bearer tokens are not sender-constrained;
  - owner notes and the engaged profile view reach a provider MCTL does not
    choose (documented, not changed);
  - the account-scoped token keeps its wide reach and has no `jti`.

  Each has an owner and a revisit trigger. The revisit trigger for the wide
  account token is "an external runtime is onboarded for an account other than
  the owner's own".

### 2. Contract: `docs/contracts/agent-job-api.md` (current behaviour)

- A versioned document, "agent job API v1", in the same layout as
  `docs/contracts/mctl-api-work-context.md`:
  - authentication and the credential matrix (account `aud=agent`, job
    `aud=agent-job` x route);
  - the job lifecycle: claim -> read -> propose/request approval/summary ->
    complete, plus job status and cost report;
  - the claim envelope fields (`jobEnvelope`);
  - per-route schemas;
  - the binding rules;
  - deadlines (`deadline` is advisory, the sweeper enforces);
  - retry, idempotency and fencing (attempt, `install_revision`);
  - deprecations (`GET /events`, sunset 2026-12-31);
  - the current error semantics: statuses, the free-text `{"error": "..."}`
    bodies, and the `policy.DenyCode` values policy refusals carry.
- **No error redesign.** Response bodies and codes stay exactly as the code
  writes them. The document records them; it does not add a `code` field or
  an enum.
- **Doc sync test.** `docs/agent_job_api_test.go` (package `docs`, the same
  pattern as `docs/compatibility_test.go`) drives `Server.Register` with a
  recording router (the `Register` parameter is already an interface with
  `Get`/`Post`), so no refactor is needed. It compares the recorded routes
  with the contract's route table, and checks that the threat model names
  every route. It fails on any difference.
- Update `docs/assistants/spec.md` (T4 row) and `docs/agent-worker.md` to link
  to the contract and the threat model.

### 3. Credential boundary (documentation only)

The owner-approved model is written into the threat model (section 1), the
contract (section 2) and the `docs/assistants/spec.md` T4 row. No code
changes.

- **Own / external runtime:** the existing account-scoped `aud=agent` token
  (`POST /api/agent/token`, admin-only, 30 days by default, 90 days maximum,
  no `jti`). The documents state its blast radius as it is today (it can
  claim, read any conversation's context, leads and events of the account,
  and call every per-job route for any job of the account; revocation is by
  blanket revocation by Telegram id). Job-level binding comes from the
  `aud=agent-job` tokens that `POST /jobs/claim` mints where a job-token
  signer is configured. Mutating actions go through the policy engine and the
  send gate regardless of the credential. The worker never receives Telegram
  session material.
- **Managed runtime (planned, #1090, ADR 0008):** a claim-only
  `aud=agent-pool` credential, then job-bound `aud=agent-job`. The documents
  mark it as design intent, not implemented. Its guard and the proof that
  pool revocation kills derived job tokens are #1090 deliverables.

### 4. Conformance runner (black box, existing fixtures and gates)

- **Claim-serving fake.** New `internal/agenteval/conformance.go`, type
  `Conformance`, an `http.Handler` that wraps a queue of the existing `Task`s:
  - `POST /jobs/claim` accepts the harness-issued token. It returns the
    next fixture's `JobEnvelope`: job id, attempt 1, conversation 1, the
    `instructions` from `Target.Instructions`, `tools` from
    `Target.JobTools`, the deadline, and a fresh random `job_token`. When the
    queue is empty it returns `{"jobs": []}` after a short hold.
  - **Routing is by identity, never by "the current fixture".** For the whole
    run `Conformance` keeps two tables, both filled at claim time and never
    pruned: `job_token -> Task` and `job_id -> Task`. A per-job request is
    resolved in this order:
    1. a job token resolves to the `Task` it was issued for, whichever
       fixture was claimed since;
    2. the harness (account-scoped) token resolves through the job id in the
       path or body (`/jobs/{id}`, `/jobs/{id}/complete`, `/jobs/{id}/cost`,
       and the job fields of the other write routes);
    3. if neither names a job (for example `GET /policy` with the harness
       token), the request goes to the one fixture that is claimed and not
       yet terminal; if there is none, or more than one, the request is
       answered 409 and recorded as a binding violation. Nothing is guessed.
  - **Late requests of a finished job.** After a job reaches a terminal
    status its `Task` stays in the tables. Its token keeps resolving to it,
    so a late request can never reach another fixture's `Task`. The status
    read (`GET /jobs/{id}`) and the cost report (`POST /jobs/{id}/cost`),
    which `finishRun` sends after completion, are answered as in production.
    A late write (propose, save lead, approval, summary, pause, complete) is
    answered 409, the fence production applies to a finished attempt, and
    does not change any score.
  - **Cross-job use.** A job token presented with another job's id in the
    path or body is answered 403 and recorded through the existing
    binding-violation recording on the `Task` that owns the token. If `Task`
    exposes no way to record from outside, a small method is added to `Task`;
    `Score`, `FixtureResult`, the violation classes and `HarnessVersion` do
    not change.
  - The harness token stands for the account-scoped `aud=agent` token and is
    accepted where production accepts it. The existing `Task` checks
    (`tools.Endpoints`, `boundBody`, guarded policy dry run) apply unchanged.

  The fake still never reaches a store, the executor or Telegram:
  `TestNoPathToEffects` is extended to cover `conformance.go`. `Score`,
  `FixtureResult`, the violation classes and `HarnessVersion` are unchanged.
- **Runner.** New `cmd/agent-conformance/main.go`, a CLI. An external author
  can `go install` it.
  - Flags or env:
    - `--suite hr-recruiter@0.1.0` (catalog plus `agenteval.LoadSuite`);
    - `--worker-cmd "<argv>"` (`AGENT_CONFORMANCE_WORKER_CMD`), *or*
      `--listen :8099` (`AGENT_CONFORMANCE_LISTEN`);
    - `--timeout` (`AGENT_CONFORMANCE_TIMEOUT`, default 32 x 3 min);
    - `--filter`;
    - `--report out.json`.
  - With `--worker-cmd`: start a loopback server, then exec the command with
    `AGENT_API_BASE_URL=<url>` and `AGENT_API_TOKEN=<harness token>`, the env
    names `cmd/agent-worker` reads. Inherit the rest of the environment
    (model credentials are the author's).
  - With `--listen`: print the base URL and token and serve the same fake.
  - **Shutdown is a drain, not a kill.** `finishRun` sends `GET /jobs/{id}`
    and `POST /jobs/{id}/cost` after the job is already terminal, so the run
    must not stop at "every fixture terminal". The run goes through these
    states:
    1. *Running:* claims are served, requests are routed as above.
    2. *Settling:* entered when every fixture is terminal or the timeout hits.
       A fixture is settled when its post-terminal status read and cost
       report have both arrived, or when no request has arrived for it within
       `--settle-quiet` (default 2 s, for black-box workers that do not send
       them). Settling ends when every fixture is settled, or after
       `--settle-max` (default 30 s) in total. A timeout here is written to
       the report as `settle_timeout: true` and a list of unsettled fixtures;
       it is informational and does not change the pass/fail rule.
    3. *Draining:* `POST /jobs/claim` now returns `{"jobs": []}` at once, so a
       long-polling worker is released. With `--worker-cmd` the command gets
       SIGTERM and then SIGKILL after `--stop-grace` (default 10 s). The HTTP
       server is shut down with `http.Server.Shutdown` and the same grace, so
       requests already in flight finish, and only then are the listener and
       the tables closed.
    4. *Scored:* the report is computed after the worker and the server have
       stopped, from everything recorded, including requests that arrived
       while draining.
    The last fixture is not special: the same states apply to it.
  - Output: the `Score` report as JSON with `harness_version`,
    `suite_digest`, `definition_digest`, per-fixture outcomes (no model text,
    as `FixtureResult` already guarantees), the settle fields above, and a
    pass/fail exit code.
- **C1 reuse.** `TestC1ObserveEval` keeps its in-process mode, unchanged. A new
  opt-in `TestC1Conformance` (`AGENT_CONFORMANCE=1`) builds `cmd/agent-worker`
  and runs it through `Conformance` as a black box. This is the C1 harness
  "run against any worker binary". The acceptance bar is the existing one:
  suite threshold, 32/32 terminal, 0 leaks, 0 binding violations, 0 wrong
  auto-sends.

## Alternatives

- **A separate claim-only `agent-runtime` credential for external runtimes (the first version of this proposal).** Rejected by the owner on 2026-11-02: own and managed are different trust boundaries, and reworking the own path would widen P5 without need. The owner-approved model is own = existing `aud=agent`, managed = `agent-pool -> agent-job` in #1090.
- **Restrict the existing `aud=agent` token to claim-only in place.** Out of scope: it would break the deployed first-party worker and change the own credential path. The wide reach of the account token is recorded as a residual risk with a revisit trigger instead.
- **Job tokens only, delivered by push to the runtime.** Out of scope: it reverses the pull model every worker and the C1 harness use.
- **Sender-constrained tokens (DPoP or mTLS).** Out of scope; recorded as a residual risk.
- **A new evaluation framework for conformance.** Rejected: the existing `agenteval` fixtures, `Task` fake and `Score` gates already define the bar. Only a claim-serving wrapper and a CLI are added.

## Platform impact

- **Migrations:** none.
- **Runtime behaviour:** none. No change to auth, token handlers, the claim handler, error bodies, runners or `Server.Register`. The server and worker binaries behave exactly as before.
- **Backward compatibility:** nothing to break. `HarnessVersion` is unchanged, so stored P4.3 eval run bindings stay comparable.
- **Deployed config:** none. No gitops change ships with the implementation. The conformance binary is not added to any image.
- **Resources:** none at runtime. The one manual 32-fixture conformance run spends model quota once, inside the existing eval budget.
- **Risks and mitigations:**
  - *Documents drift from the code.* The doc-sync tests (T1, T2) fail when a route is added or removed on one side only. Error semantics are prose and are reviewed with the code.
  - *The harness token semantics are mistaken for a new production credential.* The contract and the tool's help say the harness token mirrors `aud=agent` and exists only inside the fake. No server code reads it.
  - *Late requests mis-attributed, or lost at shutdown.* Routing by token and
    job id, and the drain sequence, are covered by T6 and T7, which are
    mutation-checked.
  - *Overlap with #1090.* None in code: #1090 owns `aud=agent-pool`, its guard and the revocation proof. This proposal only documents the planned model.
