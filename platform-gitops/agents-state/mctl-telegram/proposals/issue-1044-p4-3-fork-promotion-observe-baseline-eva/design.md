# Design: issue-1044-p4-3-fork-promotion-observe-baseline-eva

## Current state

The accepted design is in `docs/assistants/adr-forks.md`, sections
"Promotion (P4.3)" and "P4.3 decisions". It splits the work into slices S1,
S2 and S3. This proposal implements that design. It does not reopen it.

What exists in the clone (HEAD `80583cb`):

- **Fork documents and rules (P4.2).** `internal/assistant/fork.go`:
  `BuildFork`, `ValidateFork` (the fork may only narrow its base), `ForkBump`
  (patch = instructions only, minor = authority diff) and `NextForkVersion`.
  Every version has its own digest.
- **Storage.** `internal/db/agent_schema.go` creates `assistant_forks`
  (SQLite and PG). The primary key is `(user_id, name, version)`, there is a
  unique index on `(user_id, digest)`, `document_encrypted` holds the
  document, and `promotion TEXT NOT NULL DEFAULT 'observe'`.
  `internal/db/assistant_forks.go` has `ForkPromotionObserve`, the per-account
  fork lock `beginForkTx`, `InsertAssistantFork`, `GetAssistantForkByDigest`,
  `DeleteAssistantFork` and `InstallAgentFork`. Only `observe` is ever
  written.
- **Install path.** In `internal/assistantinstall/forks.go`,
  `checkForkInstall` refuses `db.AgentModeGuarded` for any fork with
  `MsgForkObserveOnly` ("P4.2 has no promotion"). `storeFork` always writes
  `ForkPromotionObserve` and alerts the owner with `forkNotice`. It is called
  from `service.go:315`.
- **Claim.** `internal/agentapi/events.go:106-113` refuses a fork claim when
  forks are disabled or `a.Mode == db.AgentModeGuarded`
  (`errForkNotRunnable`, answered with 503). `lookupFork` renders a fork from
  `(user_id, digest)` and re-runs `ValidateFork`.
- **Policy.** `internal/agent/policy/policy.go:82-88` declares
  `Input.ForkPromoted`. The comment there says no production caller sets it
  yet. Lines 542-546 treat guarded on an unpromoted fork as observe.
  `policy.Evaluate` is called from `internal/agentapi/actions.go:281` and
  `:718`, from `internal/agent/executor/executor.go:384` and `:752` (the
  send-time check), and from `internal/agenteval/fake.go:363` (the dry run,
  which sets `ForkPromoted`).
- **S1 is merged.** `internal/agenteval` contains `suite.go` (suites,
  `HarnessVersion = "agenteval/1"`, `ErrNoSuite`, `Fixture.ExpectedDecision`),
  `target.go` (`Prepare`, `ErrNothingToPromote`, `Adaptation.CheckLeads`),
  `fake.go` (a `Task` that serves the fake agent API and the guarded dry run),
  `score.go` (`Score`, `Report`) and `binding.go` (`RunBinding`, `BindingFor`,
  `Check`, `ErrBindingMismatch`). Suites live in
  `assistants/hr-recruiter/eval/{0.1.0,0.1.1}` and are pinned by
  `activeSuiteDigests` in `agenteval_test.go`. The opt-in C1 harness in
  `internal/agentworker/eval_test.go` uses the same package.
- **Tokens.** Agent audiences are `bridge`, `agent` and `agent-job`
  (`internal/auth/localjwt/issuer.go:413` `derivedAudiences`). `agent-job` is
  bound to one job and attempt (`internal/agentapi/binding.go`,
  `jobTokenAudience` in `events.go:264`). The provider is built in
  `cmd/server/main.go:1350` `selectAgentJobProvider`. There is no `agent-eval`
  audience and no `auth_time` claim: grep finds neither `AuthTime` nor
  `auth_time`.
- **Web.** The manage routes are mounted in `cmd/server/main.go:669-675`
  behind `manageAuth`. `isBrowserSignIn` (`internal/web/account.go:114`)
  identifies the self-connect credential. The self-connect token is minted
  by `ExchangeConnect` (`internal/oauth/server.go:1018`) and never gets a
  refresh token. There are no fork, eval or promotion pages.
- **Config.** `AssistantForksEnabled` / `ASSISTANT_FORKS_ENABLED`
  (`internal/config/config.go:470,556`) is wired in `main.go:653,831`.
  `ASSISTANT_FORK_EVAL_ENABLED` and `ASSISTANT_FORK_GUARDED_ENABLED` do not
  exist.
- **Migrations.** New columns use `addColumnIfMissing` in
  `internal/db/agent_schema.go`. New tables go in `agentSchemaSQLite` and
  `agentSchemaPG`. Purge is `purgeAgentData` in `internal/db/agent_domain.go`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag
  `0.121.1`, `AUTH_MODE: local-jwt`, `AGENT_ENABLED: "true"`,
  `ASSISTANT_REGISTRY_ENABLED: "true"`. No `ASSISTANT_FORK*` variable is set,
  so forks are off in production (the default is false).
- `services/labs/mctl-telegram-preview/values.yaml`: tag `main-80583cb`, the
  same agent and registry flags, no `ASSISTANT_FORK*` variable.
- `services/labs/agent-worker-preview/values.yaml`: the only agent-worker
  deployment. It points at the preview server, with `AGENT_MAX_BUDGET_USD
  "0.50"` and `AGENT_WORKER_CONCURRENCY "2"`. The services list under `labs`
  has no production agent worker. So today an eval run can only execute on
  preview, which matches the S2 exit criterion "one real run on preview".
- I did not call the mctl MCP tools. The gitops checkout was enough for
  config. I did not observe runtime status or logs.

## Proposed solution

Two PRs, matching ADR slices S2 and S3. Each is behind its own flag, and
both flags are off by default.

### S2: eval runs (`ASSISTANT_FORK_EVAL_ENABLED`)

1. **Tables** (SQLite and PG, `agent_schema.go`):
   - `assistant_fork_eval_runs(id, user_id FK CASCADE, fork_digest,
     base_digest, suite_digest, harness_version, state, created_at,
     finished_at, report_json)`. `state` is one of `queued | running |
     passed | failed | incomplete | expired | cancelled`. `report_json` holds
     the gate results and per-fixture rows only: fixture id, category,
     action, flags, leak-marker ids and cost. There is never output text.
     Indexes are `(user_id, fork_digest, created_at)` and `(state,
     created_at)`.
   - `assistant_fork_eval_tasks(run_id, fixture_id, attempt, state,
     deadline, result_json)`. One row per fixture, so the infrastructure
     retry (once, only before any tool call) is a row-level attempt bump.
   - `purgeAgentData` deletes both tables. `DeleteAssistantFork` marks the
     open runs of the deleted digests `cancelled` in the same transaction.
2. **Store** (`internal/db/assistant_fork_evals.go`):
   `CreateForkEvalRun` runs under `beginForkTx` and enforces every limit
   from the DB inside the transaction: 1 open run per account, 3 per account
   per 24 h, 20 per day globally, at most 2 scored runs per digest, a second
   only after a fail, none after a pass. It also provides
   `ClaimForkEvalTask`, `FinishForkEvalTask`, `LatestScoredForkEvalRun` and
   `ExpireForkEvalRuns`. The expiry sweep is driven by the existing
   `internal/sweeper`.
3. **Start route.** `POST /telegram/connect/manage/fork/eval` and the
   fork list section on `HandleManage`, in a new
   `internal/web/manage_forks.go`. The route requires `isBrowserSignIn`. A
   generic `account:manage` token is refused. The form names the fork
   name@version. The server reads the row and derives the digest, base and
   suite. It calls `agenteval.Prepare` up front so that `ErrNoSuite` and
   `ErrNothingToPromote` refuse before a row is written.
4. **Token audience.** Add `agent-eval` to `derivedAudiences`, with
   claims `EvalRunID` and `EvalTaskAttempt`, mirroring `JobID`/`JobAttempt`.
   Add `selectAgentEvalProvider` in `main.go`. The existing `/api/agent/v1`
   middleware keeps `ExpectedAudience: "agent"` / `"agent-job"`, so it
   refuses `agent-eval`. The eval routes accept only `agent-eval`.
5. **Worker routes.** In a new `internal/agentapi/eval.go`:
   - `POST /api/agent/v1/eval/claim` takes the `agent` worker token. It
     answers 204 while any real job is claimable, and 204 when the flag is
     off. Otherwise it claims one task, renders the fork via the existing
     `lookupFork` and `agenteval.Prepare`, and returns the job envelope with
     an `agent-eval` token.
   - `/api/agent/v1/eval/tasks/{id}/...` is served by `agenteval.NewTask(...)`
     rebuilt from the stored task. It has no executor or Telegram dependency,
     which `TestNoPathToEffects` already guards.

   On the final fixture the server calls `agenteval.Score` and writes
   `passed` or `failed`. The worker never reports a verdict.
6. **Worker.** `internal/agentworker/worker.go` polls `eval/claim` only
   when its real claim returned nothing. It runs the task through the same
   invoker. It needs no new config.
7. **Alerts and audit.** On start and finish, the owner gets a bot-chat
   notice (fork ref, run id, verdict) and an audit row with the same fields,
   never text.

### S3: promotion (`ASSISTANT_FORK_GUARDED_ENABLED`)

1. **`auth_time`.** `ExchangeConnect` stamps an `AuthTime` claim on the
   authorization code. The value is when the server verified Telegram's
   id_token. The claim is copied onto the access token and exposed as
   `auth.Identity.AuthTime`. A token without it fails freshness checks
   closed.
2. **Columns.** Add to `assistant_forks` via `addColumnIfMissing`:
   `promoted_at`, `promoted_eval_run_id`, `revoked_at` and
   `written_by_client`. `promotion` gains the values `promoted` and
   `revoked`. The document and digest stay immutable. Add a new append-only
   table `assistant_fork_promotion_events(id, user_id, fork_digest, kind,
   eval_run_id, client_id, jti, at)`, which is also purged.
3. **Store.** Add `PromoteAssistantFork(ctx, userID, digest, runID,
   expectedRevision, switchGuarded, meta)` and `RevokeAssistantFork(...)`.
   Each runs in one transaction under `beginForkTx`. The re-checks are:
   the run is `LatestScoredForkEvalRun(digest)`, its state is `passed`, and
   `agenteval.RunBinding.Check` passes against the binding rebuilt from the
   fork row and the current suite. The base lifecycle must be `published`.
   The optional mode switch reuses the install revision CAS that
   `InstallAgentFork` uses. Revocation sets the mode to `observe` when the
   install pins that digest in `guarded`. Add a `ForkPromoted(ctx, userID,
   digest) (bool, error)` read.
4. **Pages.** `GET`/`POST
   /telegram/connect/manage/fork/{name}/{version}/promote` and `POST
   .../revoke` go in `internal/web/manage_forks.go` with
   `Cache-Control: no-store`. The page shows:
   - the authority diff, from a new pure function
     `assistant.AuthorityDiff(base, fork)` next to `ValidateFork` (tools,
     intents and tiers, `userOverride`, limits and ceilings, disclosure,
     variable disclosure);
   - the collapsed instructions, with a line diff against the last promoted
     version;
   - the gate table from `report_json`.

   Promote requires `isBrowserSignIn`, `account:manage`, `AuthTime` within
   15 minutes, the ticked box and the typed slug. Revoke requires only
   `account:manage`.
5. **The four conditional refusals.** Each reads
   `ForkPromoted(user, digest)`. A lookup error reads as false, and the
   result is ANDed with the `ASSISTANT_FORK_GUARDED_ENABLED` flag.
   - `checkForkInstall` (`assistantinstall/forks.go`) allows guarded when the
     pinned digest is promoted. It also refuses a pin move to an unpromoted
     digest while the mode is guarded.
   - The claim (`agentapi/events.go:110`) refuses guarded only when the fork
     is not promoted.
   - `actions.go:281,718` set `policy.Input.ForkPromoted`. `policy.Evaluate`
     stays pure.
   - `executor.go:752` (send time) and `:384` set `ForkPromoted` the same
     way, so an auto-send queued before a revocation is held.
6. **Notices.** `forkNotice` keeps saying a new version runs in observe.
   Promote and revoke send their own notice and audit entry. Update
   `MsgForkObserveOnly` to say "until it is promoted on the manage page".
7. **Docs.** Add forks, promotion and the two new flags to
   `docs/assistants/spec.md`. Mark S2/S3 done in the ADR.

Why this way: it is the owner-accepted ADR. The server renders, scores and
binds, so the worker or the user cannot forge a pass. One package
(`agenteval`) serves both the harness and production. Every gate is
re-checked in the same transaction that changes state.

## Alternatives

- **Run the eval as a Kubernetes Job or accept an operator-uploaded result.**
  The ADR rejected this. A Job spec would carry the decrypted instructions
  and need new RBAC and a credential. An upload can be forged and shows
  private text to the operator.
- **Use a fixed "N approved drafts in observe" rule instead of an eval.** The
  issue and the ADR exclude this. It depends on traffic, rewards volume
  rather than adversarial coverage, and does not exercise leaks or binding.
- **Promote through an MCP tool or `/mctl`.** Rejected. `send_message` can
  write to Saved Messages as the account, so a prompt-injected MCP client
  could promote. Only the browser sign-in with a fresh `auth_time` proves the
  human owner.
- **Reuse the `agent-job` audience for eval tasks.** Rejected. A real job
  token could then write eval results, and an eval token could reach real
  effect routes.

## Platform impact

- **Migrations.** These are additive only: two eval tables, one events
  table, and four nullable columns on `assistant_forks` added via
  `addColumnIfMissing`, on both SQLite and PG. Existing rows keep
  `promotion = observe`. There is no backfill.
- **Backward compatibility.** With `ASSISTANT_FORK_EVAL_ENABLED` and
  `ASSISTANT_FORK_GUARDED_ENABLED` off (the default), and
  `ASSISTANT_FORKS_ENABLED` off as deployed today, behaviour is unchanged:
  the four refusals evaluate exactly as in P4.2. Old access tokens lack
  `auth_time`, so promotion asks for a fresh sign-in. Nothing else reads the
  claim.
- **Cost.** Eval runs spend the platform's model budget through the worker
  credential pool. The worst case is bounded by 20 runs per day, times the
  fixture count, times `AGENT_MAX_BUDGET_USD` per task ($0.50 on preview).
  Eval claims yield to real jobs.
- **Load.** Each `policy.Evaluate` call site adds one indexed lookup by
  `(user_id, digest)`, made only when the profile runs a fork in guarded
  mode.
- **Risks and mitigations.**
  - *An eval token reaches a real route.* Mitigation: separate audience
    providers, plus a test that every `/api/agent/v1` route refuses
    `agent-eval`.
  - *A stale promotion survives a revocation in the send queue.* Mitigation:
    the send-time check at `executor.go:752` reads the promotion.
  - *Model output leaks the instructions into storage.* Mitigation: the
    report schema has no text fields, and a test asserts no fixture output
    string is persisted.
  - *Multi-replica limit races.* Mitigation: the counts run inside
    `beginForkTx` for the per-account limits, and a global count runs in the
    same transaction. An occasional 21st run is tolerated. See Open
    questions in requirements.md.
  - *A suite changes under a promotion.* Mitigation: `RunBinding` includes
    `suite_digest`, and suites are immutable per base version (pinned test).
