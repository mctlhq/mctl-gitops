# Design: issue-1403-p4-3-fork-promotion-observe-baseline-eva

## Provenance

This is the proposal for #1403, the re-file of #1044 (which stays open as the
roadmap reference; its DevLoop is Completed without a live grant and cannot be
restarted). Scope and intent are the same as the #1044 proposal refreshed on
2026-11-22 (`platform-gitops/agents-state/mctl-telegram/proposals/issue-1044-p4-3-fork-promotion-observe-baseline-eva/`),
which this one supersedes. Every code anchor below was re-read on 2026-11-22
in a fresh clone of mctl-telegram `main` at `eb1ac9c` (merge of PR #1357,
2026-11-22 23:27 +0100). Differences against the #1044 refresh (which was
anchored at `0ef3857a`): `checkPoolShape` is at `localjwt/pool.go:59` (was
`:65`), `selectAgentProvider` at `cmd/server/main.go:1475` (was `:1468`), the
`errForkNotRunnable` answer in the claim path at `agentapi/events.go:387`
(was `:349`), the preview images are on `main-eb1ac9c`, and a PA worker
service `agent-worker-pa-preview` now exists in gitops. Everything else
(including that S2 and S3 are unimplemented) is unchanged: grep on `eb1ac9c`
finds no `agent-eval`, `auth_time`/`AuthTime`, `ASSISTANT_FORK_EVAL_ENABLED`,
`ASSISTANT_FORK_GUARDED_ENABLED` or `assistant_fork_eval` anywhere in Go code,
and no production caller sets `policy.Input.ForkPromoted`.

Anchors drift: re-read them before implementing.

## Current state

The accepted design is in `docs/assistants/adr-forks.md`, sections
"Promotion (P4.3)" and "P4.3 decisions". It splits the work into slices S1,
S2 and S3. This proposal implements that design. It does not reopen it.

What exists on mctl-telegram `main` (`eb1ac9c`; all paths and line numbers
below were read from that commit on 2026-11-22):

- **Fork documents and rules (P4.2).** `internal/assistant/fork.go`:
  `BuildFork`, `ValidateFork` (the fork may only narrow its base), `ForkBump`
  (patch = instructions only, minor = authority diff) and `NextForkVersion`.
  Every version has its own digest.
- **Storage.** `internal/db/agent_schema.go` creates `assistant_forks`
  (SQLite at `:852`, PG at `:1227`). The primary key is
  `(user_id, name, version)`, there is a unique index on
  `(user_id, digest)`, `document_encrypted` holds the document, and
  `promotion TEXT NOT NULL DEFAULT 'observe'`.
  `internal/db/assistant_forks.go` has `ForkPromotionObserve` (`:26`), the
  per-account fork lock `beginForkTx` (`:80`), `InsertAssistantFork` (`:156`),
  `GetAssistantForkByDigest` (`:252`), `ListAssistantForks` (`:288`),
  `DeleteAssistantFork` (`:319`) and `InstallAgentFork` (`:363`). Only
  `observe` is ever written.
- **Install path.** In `internal/assistantinstall/forks.go`,
  `checkForkInstall` (`:162-168`) refuses `db.AgentModeGuarded` for any fork
  with `MsgForkObserveOnly` (`:30`, "P4.2 has no promotion"). `storeFork`
  (`:274`) always writes `ForkPromotionObserve` and alerts the owner with
  `forkNotice`. `checkForkInstall` is called from `service.go:356`.
- **Claim.** `accountInstructions` in `internal/agentapi/events.go:113-119`
  refuses a fork claim when forks are disabled or
  `a.Mode == db.AgentModeGuarded` (`errForkNotRunnable`, `:93`; answered with
  503 in the claim handler's error switch, `:387`). `lookupFork` (`:198`) renders a fork from
  `(user_id, digest)` and re-runs `ValidateFork`. A managed-runtime pool
  credential claims through `handlePoolClaim` (`:468`), which renders each
  account's instructions through the same path before claiming.
- **Policy.** `internal/agent/policy/policy.go:83-89` declares
  `Input.ForkPromoted`. The comment there says no production caller sets it
  yet (`docs/spikes/assistant-builder-ui-reference.md:158` repeats this).
  Lines 570-575 treat guarded on an unpromoted fork as observe.
  `policy.Evaluate` is called from `internal/agentapi/actions.go:304` and
  `:758`, from `internal/agent/executor/executor.go:397` and `:790` (the
  send-time check), and from `internal/agenteval/fake.go:385` (the dry run,
  which sets `ForkPromoted` at `:395`). None of the four production call
  sites sets `ForkPromoted`.
- **S1 is merged.** `internal/agenteval` contains `suite.go` (suites,
  `HarnessVersion = "agenteval/1"`, `ErrNoSuite`, `Fixture.ExpectedDecision`),
  `target.go` (`Prepare`, `ErrNothingToPromote`, `Adaptation.CheckLeads`),
  `fake.go` (a `Task`, `NewTask` at `:68`, that serves the fake agent API and
  the guarded dry run), `score.go` (`Score`, `Report`), `binding.go`
  (`RunBinding`, `BindingFor`, `Check`, `ErrBindingMismatch`) and
  `conformance.go` (a queue of suite fixtures served as the claim side of the
  agent API, so a worker can be run against the C1 suite as a black box).
  Suites live in `assistants/hr-recruiter/eval/{0.1.0,0.1.1}` and are pinned
  by `activeSuiteDigests` in `agenteval_test.go:28`. `TestNoPathToEffects`
  (`:604`) guards that the package has no path to the executor or Telegram.
  The opt-in C1 harness in `internal/agentworker/eval_test.go` uses the same
  package.
- **Tokens.** Credential audiences are `bridge`, `agent`, `agent-job`,
  `agent-pool` (`internal/auth/localjwt/issuer.go:431` `derivedAudiences`,
  which `needsRevocationCheck` reads) and `pa-job` (`localjwt/pajob.go:24`,
  deliberately not in `derivedAudiences`: `Provider` refuses any token with
  the audience or a PA claim, `hasPAJobClaims`, `issuer.go:336`, and only
  `PAJobVerifier` accepts it, checking revocation by the inherited pool jti).
  `agent-job` is bound to one job and attempt through the signed claims
  `JobID`/`JobAttempt`/`ConversationID`/`JobTools` (`issuer.go:92-101`,
  `internal/agentapi/binding.go`, `jobTokenAudience` at `events.go:271`).
  `agent-pool` is claim-only: `checkPoolShape` (`localjwt/pool.go:59`)
  refuses a pool token with job claims, and `requireNotPool`
  (`agentapi/binding.go:123`) wraps every `/api/agent/v1` route except
  `POST /jobs/claim`. The agent providers are built in `cmd/server/main.go`
  (`selectAgentProvider` `:1475`, `selectAgentJobProvider` `:1450`, chained
  at `:816`, `wireManagedPool` at `:841`, mounted at `:846`). The worker-token
  revocation cache is one shared `RevocationCache` (`cmd/server/main.go:551`)
  whose snapshot is bounded by `MaxRevocationSnapshotAge` (15 s,
  `localjwt/revocation.go:34`): past that bound every worker-token check fails
  as unverifiable (#1346). There is no `agent-eval` audience and no
  `auth_time` claim: grep finds neither `AuthTime` nor `auth_time`.
- **Personal Assistant (#1313, #1318).** The PA worker is a separate mode of
  the same binary (`AGENT_WORKER_PA`, `cmd/agent-worker/main.go:104-111`,
  `agentworker.PAWorker.loop` in `parunner.go`). It claims with the pool
  credential from `POST /api/pa/v1/jobs/claim` and calls the server's tool
  executor with `pa-job` tokens. It does not run `agentworker.Worker.Loop`,
  and the PA run loop is built in `cmd/server/pa_wiring.go`. Preview has
  `PA_ENABLED=false`.
- **Web.** The manage routes are mounted in `cmd/server/main.go:659-670`
  behind `manageAuth`. `isBrowserSignIn` (`internal/web/account.go:120`)
  identifies the self-connect credential. The self-connect token is minted
  by `ExchangeConnect` (`internal/oauth/server.go:1041`) and never gets a
  refresh token. There are no fork, eval or promotion pages.
- **Config.** `AssistantForksEnabled` / `ASSISTANT_FORKS_ENABLED`
  (`internal/config/config.go:511,805`) is wired in `main.go:642,827`.
  `ASSISTANT_FORK_EVAL_ENABLED` and `ASSISTANT_FORK_GUARDED_ENABLED` do not
  exist.
- **Migrations.** New columns use `addColumnIfMissing` in
  `internal/db/agent_schema.go`. New tables go in `agentSchemaSQLite` and
  `agentSchemaPG`. Purge is `purgeAgentData` in `internal/db/agent_domain.go:769`.
- **Sweepers.** `cmd/server/main.go:419-436` starts the `internal/sweeper`
  loops (`Sessions`, `AuditLog`, `RefreshTokens`, `AgentRetention`,
  `JobLeads`).

Deployed state checked (read-only, `$MCTL_GITOPS_ROOT` = mctl-gitops
`platform-gitops/`, `services/labs/`):

- `services/labs/mctl-telegram/values.yaml`: image tag `0.142.0`,
  `ASSISTANT_REGISTRY_ENABLED: "true"`. No `ASSISTANT_FORK*` variable is set
  (grep over `services/labs` finds none), so forks are off in production
  (default false).
- `services/labs/mctl-telegram-preview/values.yaml`: tag `main-eb1ac9c`,
  `ASSISTANT_REGISTRY_ENABLED: "true"`, `MANAGED_RUNTIME_ENABLED: "true"`
  (`MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`), `PA_ENABLED: "false"`, no
  `ASSISTANT_FORK*` variable.
- `services/labs/agent-worker-preview/values.yaml` (tag `main-eb1ac9c`,
  `AGENT_MAX_BUDGET_USD: "0.50"`) and
  `services/labs/agent-worker-managed-preview/values.yaml` (tag
  `main-eb1ac9c`, `AGENT_POOL_MODE: "true"`, `AGENT_MAX_BUDGET_USD: "0.25"`).
  `services/labs/agent-worker-pa-preview/` also exists (PA mode; it does not
  run `Worker.Loop` and is not touched by this design). There is no
  production agent worker under `labs`, so an eval run can execute only on
  preview, matching the S2 exit criterion "one real run on preview".
- mctl MCP tools: not called. The gitops checkout covered configuration; I
  did not observe runtime status, pod state or logs, and did not run the
  mctl-telegram tests. Runtime state is therefore unobserved, not absent.

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
4. **Token audience.** Add `agent-eval` to `derivedAudiences`
   (`issuer.go:431`) so the revocation check always runs for it. Its claims
   are new and its own: `EvalRunID` and `EvalTaskAttempt`. They do not reuse
   `JobID`/`JobAttempt`, because `jobBound` (`agentapi/binding.go`) and
   `checkPAJobShape` read those as "a real or PA job credential". The token
   inherits the claiming worker credential's `jti` and `orig_iat`, as
   `mintJobToken` does, so revoking the worker revokes its eval tokens. Add
   `selectAgentEvalProvider` next to `selectAgentJobProvider` in `main.go`
   and chain it only for the eval routes, never into `agentProvider`. Three
   refusals mirror what #1313 did for `pa-job`:
   - `Provider.Authenticate` refuses a token with the `agent-eval` audience or
     an eval claim (a `hasEvalClaims` next to `hasPAJobClaims`), whatever its
     audience policy is. With `OAUTH_JWT_AUDIENCE` unset the audience check
     passes any audience, so without this an eval token would act as the
     account's Telegram identity on every `Provider`-guarded surface.
   - `checkPoolShape` (`pool.go:59`) refuses a pool token with eval claims.
   - A new `EvalVerifier`, modelled on `PAJobVerifier`, is the only acceptor:
     exact audience, exact shape, run and attempt bound, revocation checked
     with the inherited jti.

   The existing `/api/agent/v1` middleware keeps accepting only `agent`,
   `agent-job` and `agent-pool`, so it refuses `agent-eval`. The eval task
   routes accept only `agent-eval`. The PA routes (`/api/pa/v1`) keep
   accepting only `pa-job`, so neither side can reach the other.
5. **Worker routes.** In a new `internal/agentapi/eval.go`:
   - `POST /api/agent/v1/eval/claim` is registered beside `/jobs/claim`, as
     the second route a pool credential may call (add it to `requireNotPool`'s
     exception). It accepts the account `agent` token and the managed `agent-pool`
     credential; both preview workers use one of them. An account token may
     claim only tasks of its own account. A pool credential may claim tasks of
     any account, with the same round-robin discipline as `handlePoolClaim`.
     It answers 204 while any real job is claimable for the caller's scope
     (the same candidate query the real claim uses), and 204 when
     `ASSISTANT_FORK_EVAL_ENABLED` is off, `ASSISTANT_FORKS_ENABLED` is off or
     `AGENT_KILL_SWITCH` is on. Otherwise it claims one task, renders the fork
     via the existing `lookupFork` and `agenteval.Prepare` (the rendered
     instructions never come from the request), and returns a job envelope
     with an `agent-eval` token. The "real queue empty" check and the task
     claim must run as one decision per request, so a real job arriving
     between them is served on the next poll; an eval task never delays a real
     job by more than one poll interval.
   - `/api/agent/v1/eval/tasks/{id}/...` is served by `agenteval.NewTask(...)`
     rebuilt from the stored task, behind the `EvalVerifier`. It has no
     executor or Telegram dependency, which `TestNoPathToEffects` already
     guards. The task routes live outside `Register`'s `toolGate` and outside
     `requireNotPool`, because `Register` mounts only `agent`/`agent-job`
     identities.

   On the final fixture the server calls `agenteval.Score` and writes
   `passed` or `failed`. The worker never reports a verdict.
6. **Worker.** `agentworker.Worker.Loop` (`worker.go:172`) polls `eval/claim`
   only when its real claim returned no job and a slot is free. It runs the
   eval task through the same invoker. `PAWorker.loop` (`parunner.go`) is not
   changed: the PA worker is a separate process mode that does not run
   `Worker.Loop`, and it never polls `eval/claim`. The eval path needs no new
   worker config.
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
5. **The four conditional refusals, through one helper.** Each reads
   `ForkPromoted(user, digest)` through a single helper
   (`forkRunsGuarded(ctx, store, flag, userID, profile) bool`, in a small
   package the four sites already import, for example `internal/assistant`
   or `internal/db`), so no site can compute "promoted" its own way. A lookup error reads as false, and the
   result is ANDed with the `ASSISTANT_FORK_GUARDED_ENABLED` flag.
   - `checkForkInstall` (`assistantinstall/forks.go`) allows guarded when the
     pinned digest is promoted. It also refuses a pin move to an unpromoted
     digest while the mode is guarded.
   - The claim (`accountInstructions`, `agentapi/events.go:113-119`, which
     `handleClaimJobs` and `handlePoolClaim` both go through) refuses guarded
     only when the fork is not promoted.
   - `actions.go:304,758` set `policy.Input.ForkPromoted`. `policy.Evaluate`
     stays pure.
   - `executor.go:790` (send time) and `:397` set `ForkPromoted` the same
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

### Cross-cutting edits and non-regression

Four edits reach code that live Personal Assistant, managed-runtime and
worker-revocation slices also use. The design keeps each additive and
refusing by default, and the tasks carry an explicit acceptance check for it.

1. **`localjwt` audience (`agent-eval`).** Compared with `pa-job`: `pa-job`
   is not in `derivedAudiences` because `Provider` refuses it before the
   revocation check. `agent-eval` is the opposite case: it is minted from a
   worker credential and must be revoked with it, so it goes into
   `derivedAudiences`, and the revocation path reads its inherited `jti`.
   The change to `needsRevocationCheck` only adds a match for a new audience
   string, so the result for `bridge`, `agent`, `agent-job`, `agent-pool` and
   `pa-job` tokens is unchanged. Because `MaxRevocationSnapshotAge` (#1346)
   fails worker-token checks closed when the snapshot is stale, eval tokens
   inherit that: a stale snapshot refuses the eval route, never allows it.
   No new cache or TTL is introduced.
2. **Eval claim route.** The pool credential is claim-only today
   (`requireNotPool`). The exception list grows by exactly one route,
   `POST /eval/claim`, and `pool_claim_only` stays the refusal for every
   other route. `handlePoolClaim`, `handleClaimJobs` and
   `/api/pa/v1/jobs/claim` are not edited. The eval claim must not take the
   `managed` per-account in-flight cap or the managed budget ledger, and an
   eval task spends from a separate budget line (see Platform impact), so a
   managed account's real jobs are never starved by an eval.
3. **Worker polling order.** Real claim first, eval claim only on an empty
   result. In pool mode the real claim already walks the candidate order, so
   the eval poll adds one request per empty poll window, not per job. The PA
   worker mode is untouched.
4. **One helper for the four fork-guarded refusal sites.** A promotion lookup
   error reads as "not promoted" at every site, and the helper is pure over
   its inputs, so `policy.Evaluate` keeps its purity and the PA policy paths
   (which never set a fork profile) are not reached.

Acceptance check, stated as a task-level criterion: with
`ASSISTANT_FORK_EVAL_ENABLED` and `ASSISTANT_FORK_GUARDED_ENABLED` off, the
existing agentapi, localjwt, managed-runtime and PA test suites
(`internal/auth/localjwt`, `internal/agentapi`, `internal/pa`,
`cmd/server` PA and pool wiring tests, `internal/agentworker` including
`parunner_test.go`) pass unmodified, and a new table test proves that every
token audience (`agent`, `agent-job`, `agent-pool`, `pa-job`, `bridge`,
`agent-eval`) gets the same accept or refuse answer on every route group
before and after the change, except the new eval routes. A PA slice must not
need a test edit to keep passing.

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
  fixture count, times `AGENT_MAX_BUDGET_USD` per task ($0.50 on the account
  worker, $0.25 on the managed worker, on preview). Eval tasks must not be
  charged to a managed account's daily budget.
  Eval claims yield to real jobs.
- **Load.** Each `policy.Evaluate` call site adds one indexed lookup by
  `(user_id, digest)`, made only when the profile runs a fork in guarded
  mode.
- **Risks and mitigations.**
  - *An eval token reaches a real route.* Mitigation: separate audience
    providers, `Provider` and `checkPoolShape` refuse eval claims, and a test
    that every `/api/agent/v1` and `/api/pa/v1` route refuses `agent-eval`.
  - *An eval change regresses a live PA or managed slice.* Mitigation: the
    non-regression criterion above, with the existing suites unmodified.
  - *A stale promotion survives a revocation in the send queue.* Mitigation:
    the send-time check at `executor.go:790` reads the promotion.
  - *Model output leaks the instructions into storage.* Mitigation: the
    report schema has no text fields, and a test asserts no fixture output
    string is persisted.
  - *Multi-replica limit races.* Mitigation: the counts run inside
    `beginForkTx` for the per-account limits, and a global count runs in the
    same transaction. An occasional 21st run is tolerated. See Open
    questions in requirements.md.
  - *A suite changes under a promotion.* Mitigation: `RunBinding` includes
    `suite_digest`, and suites are immutable per base version (pinned test).
