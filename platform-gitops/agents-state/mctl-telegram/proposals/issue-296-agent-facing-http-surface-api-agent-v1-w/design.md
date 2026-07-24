# Design: issue-296-agent-facing-http-surface-api-agent-v1-w

## Current state

This section documents what actually exists in the clone at HEAD `e4e7928`
(2026-07-24), read directly rather than assumed. A prior proposal in this
same directory (dated 2026-07-19) described a codebase with no
`internal/agentapi` package; that snapshot is stale and this design
supersedes it.

**The auth-audience pattern this surface reuses.** `internal/auth/identity.go`
defines the narrow `auth.Provider` interface
(`Authenticate(*http.Request) (*Identity, error)`), and
`internal/auth/middleware.go`'s `Middleware(p, required, m)` wraps any
handler: on a provider error it always responds 401 (never falls through);
on `nil, nil` with `required=true` it also 401s; only a non-nil identity
proceeds. `internal/auth/localjwt/issuer.go` implements both the signer
(`Issuer.Mint`) and the verifier (`Provider.Authenticate`, which chains
`Verify` for signature/issuer/expiry then `CheckAudience` for the `aud`
claim). This one provider type is instantiated three separate times in
`cmd/server/main.go` with three different `ExpectedAudience` values —
unset/generic for `/mcp` (`selectProvider`), `"bridge"` for `/bridge`
(`selectBridgeProvider`, lines ~595-640), and `"agent"` for `/api/agent/v1`
(`selectAgentProvider`, lines 682-710+). All three share the same
fail-closed posture: if the active `AUTH_MODE` needs `OAUTH_JWT_SECRET` and
it is unset, the provider is `rejectAllProvider(...)`, not a silent
downgrade.

**`internal/agentapi` (already built).** Ten files, ~2100 lines:

- `server.go` — `Server` struct (`Store *db.Store`, `Queue *queue.Queue`,
  `Profile OwnerProfileProvider`, `GlobalKill bool`, plus private
  `longPollTimeout`/`jobVisibility`/`m`), `New(...)` constructor,
  `WithProfile`/`WithLongPollTimeout` chaining setters, and `Register(mux
  registrar)` which binds all twelve routes the issue asks for onto a
  `registrar` interface (`Get`/`Post`) so the package never imports `chi`
  directly — the same indirection `internal/web` uses.
- `tokenhandler.go` — `NewAgentTokenHandler(secret, issuer)` implements
  `POST /api/agent/token`: requires an already-authenticated caller (regular
  MCP chain) with scope `admin:users`, mints a token for the
  request-supplied `telegram_id` (deliberately not the caller's own
  identity — an admin provisions a worker credential, they do not
  self-mint), TTL default 30 days / max 90 days (`defaultAgentTokenTTL`,
  `maxAgentTokenTTL`), `aud=["agent"]`.
- `events.go` — `GET /events` (long-poll claim via `Queue.Claim`, 1s
  re-poll tick, returns `{"jobs":[...]}`, 200 always, empty array on
  timeout or client disconnect), `GET /event/{eventID}` (full event body),
  `POST /jobs/{id}/complete` (the durable-result invariant: `status
  =completed` requires a pre-existing `agent_actions` row
  (`HasAgentActionForJob`) or a saved lead (`HasJobLeadForJob`) for that
  `job_id`, else 409; `failed`/`ignored` need neither).
- `actions.go` — `POST /actions/propose_reply` (conversation-derived peer
  only; runs `policy.Evaluate`; three-way branch to
  `Deny`/`RequireApproval`/`Allow` with an approval-code allocation loop
  for the approval path, idempotent on `(job_id, action_type)` via
  `InsertAgentAction`'s conflict handling), `POST /leads` (upsert),
  `POST /actions/request_owner_approval` and `POST /notify/summary`
  (share `handleOwnerFacing`: policy still evaluated for the kill-switch/
  mode/autopilot gates even though owner-facing actions always resolve to
  `Allow` once past those gates; `InsertOwnerNotification` is idempotent
  per `action_id` to survive job redelivery).
- `conversations.go` — `GET /conversations/{id}/context` (conversation row
  + up to 100 recent messages + associated lead in one response),
  `GET /leads/{id}`.
- `misc.go` — `GET /policy` (advisory mirror of the caller's
  `AgentProfile` mode/limits plus the kill-switch flag; the issue's stated
  purpose — "so the worker/model can reason about what it's allowed to
  propose" — matches exactly, with `policy.Evaluate` remaining the sole
  authority server-side), `GET /recruiters/{peer}` (501 when
  `Server.Profile == nil`, matches the issue's explicit interface seam for
  #297), `POST /autopilot/pause` (`{"paused": bool}`, defaults to `true`
  on an empty body).
- `json.go` — `decodeStrict` (the issue's "strict JSON schema validation":
  `json.Decoder.DisallowUnknownFields()` + `http.MaxBytesReader` capped at
  1 MiB), `writeJSON`/`writeJSONError`, `identity()` (401 if
  `auth.From(ctx)` is nil — defensive, since the outer middleware already
  guarantees this in production), and the `audit()` wrapper over
  `Store.LogToolCall`.
- `approvalcode.go` — 6-character approval code generation used by the
  `RequireApproval` path.
- `server_test.go` / `tokenhandler_test.go` — 773 + 112 lines of
  `httptest`-based tests, all passing as read (not independently re-run in
  this read-only investigation, but structurally sound and internally
  consistent with the handlers they exercise).

**Wiring** (`cmd/server/main.go`, ~lines 326-343): mounted only when
`cfg.AgentEnabled` (`AGENT_ENABLED`, default `false`,
`internal/config/config.go`). The mint endpoint sits on the *regular* MCP
auth chain (`auth.Middleware(provider, true, m)`), the agent surface itself
sits behind `auth.Middleware(agentProvider, true, m)` where `agentProvider
:= selectAgentProvider(cfg, store)`. `agentSrv.GlobalKill = cfg.AgentKillSwitch`
wires the env-only kill switch in as a plain field, matching the pattern
already used for `mcpSrv.MediaDownloadMaxBytes` elsewhere in this file.

**Dependencies this package reuses without modification** (all merged per
the issue body): `internal/agent/queue` (`Queue.Claim`/`Queue.Complete`,
metrics-wrapped facade over `internal/db/agent_jobs.go`'s
`ClaimAgentJobs`/`CompleteAgentJob`, which do the real `SKIP LOCKED`
claim + compare-and-set completion with the `attempt` fencing counter);
`internal/agent/policy` (`policy.Evaluate`, pure function over
`policy.Input{Profile, Conversation, Action, RecentAgentSends, GlobalKill,
Now}`); `internal/db/agent_domain.go`,
`agent_actions.go`, `agent_events.go` (typed store accessors and
`Ensure`/`Get`/`Upsert`/`Has*` methods); `internal/db/store.go`'s
`LogToolCall` (hash-chained audit, `internal/db/audit_chain.go`).

**Confirmed gaps against the issue text** (see requirements.md's
Acceptance criteria / Open questions for the full reasoning):

1. `internal/agentapi/json.go`'s `audit()` helper and every call site
   (`events.go`, `actions.go`, `conversations.go`, `misc.go`) pass bare
   tool names (`"get_events"`, `"propose_reply"`, `"save_job_lead"`,
   `"complete_agent_job"`, `"get_policy"`, `"get_recruiter_profile"`,
   `"pause_autopilot"`, `"get_lead"`, `"get_conversation_context"`,
   `"get_event"`, `"request_owner_approval"`, `"send_owner_summary"`) with
   no `agent.` prefix, contradicting the issue's explicit
   `agent.<name>` convention. Every other privileged surface in this
   codebase that calls `LogToolCall` uses its own convention already
   (`internal/oauth` uses `connect:...`, `internal/mcp` passes the bare MCP
   tool name) — so this package not prefixing is an inconsistency
   specifically against *this issue's* stated requirement, not against a
   codebase-wide convention.
2. No httptest in this codebase mounts the real `selectAgentProvider` (or
   `selectBridgeProvider`) chain and proves cross-audience rejection.
   `server_test.go`'s `testHarness.do` injects `*auth.Identity` directly
   into the context, bypassing `auth.Middleware` and `localjwt.Provider`
   entirely — appropriate for testing handler logic, but it means the
   audience-isolation behavior the issue calls out by name
   ("bridge/API tokens must 403 here, and agent tokens must 403 on
   non-agent routes") has zero direct test coverage today, only the
   generic unit coverage of `localjwt.CheckAudience` in
   `internal/auth/localjwt/issuer_test.go` (`TestCheckAudience`), which
   never touches this package's routes or `cmd/server`'s wiring.
3. No test sends a structurally invalid POST body (malformed JSON, or a
   JSON object with an extra field) to confirm `decodeStrict` actually
   yields 400-not-500 through the handlers. Existing tests cover
   domain-level validation (bad `status`, empty `text`, non-numeric
   `limit=`) but not the schema-shape validation itself.

## Proposed solution

Because the substantial majority of the issue is already correctly
implemented and tested, this proposal is intentionally scoped to closing
the three gaps above rather than re-architecting anything. All changes stay
inside `internal/agentapi` and `cmd/server` (a small `_test.go` addition),
matching this codebase's existing package boundaries.

1. **Prefix audit tool names with `agent.`.** Change
   `internal/agentapi/json.go`'s `audit()` helper to prepend `"agent."` to
   `tool` once, in the single choke point every handler already calls
   through — no call site needs to change. This is the minimal,
   single-point fix: `s.Store.LogToolCall(ctx, userID, "agent."+tool, "",
   status, errMsg, "")`. Chosen over editing every call site individually
   because it guarantees no handler can be added later that forgets the
   prefix, and it is a one-line diff against a file that already exists
   for exactly this purpose (every handler already funnels through
   `s.audit`).

2. **Add end-to-end audience-isolation tests.** Add a new
   `cmd/server/agentapi_wiring_test.go` (or extend `main_test.go`) that:
   builds a real `localjwt.Issuer`/`Provider` pair the way
   `selectAgentProvider`/`selectBridgeProvider` do, mints a `aud=bridge`
   token and a `aud=agent` token, mounts a minimal router reproducing the
   two provider-gated mounts, and asserts: (a) the bridge token against an
   agent-provider-gated handler is rejected (401, matching today's actual
   `auth.Middleware` behavior — see the status-code decision recorded in
   requirements.md's Open Question 1); (b) the agent token against a
   bridge-provider-gated handler is rejected the same way; (c) the agent
   token against the agent-provider-gated handler succeeds. This is
   deliberately placed at the `cmd/server` level (or as a small new
   `internal/agentapi` test that constructs a real `localjwt.Provider`
   instead of injecting identity directly), not inside the existing
   `server_test.go` harness, because the whole point is to exercise the
   piece `server_test.go` currently bypasses.

3. **Add schema-validation edge-case tests.** Extend
   `internal/agentapi/server_test.go` with: a `POST /actions/propose_reply`
   with a body containing an unknown field (e.g. `{"conversation_id":1,
   "text":"hi","peer_tg_id":999}`) asserting 400 — this one doubles as the
   "no client-supplied peer is ever honored" test the issue explicitly
   asks for, since `peer_tg_id` is not a field `proposeReplyRequest`
   declares and `decodeStrict` must reject it outright rather than
   silently ignore it; a request with a truncated/invalid JSON body
   asserting 400; and a body exceeding `maxRequestBodyBytes` (1 MiB)
   asserting 400, not a panic or 500 from `http.MaxBytesReader`'s
   `io.ErrUnexpectedEOF`.

4. **Record, do not change, the 401-vs-403 behavior.** Per requirements.md
   Open Question 1, changing `auth.Middleware`'s status code for
   audience-mismatch specifically (as opposed to every other
   `Authenticate` failure) would touch all three audiences' shared
   middleware and is out of proportion to this issue. The task list below
   captures this as an explicit human-reviewable decision point rather than
   silently diverging from the issue text.

5. **No change to `GET /recruiters/{peer}`.** The 501 stub and the
   `OwnerProfileProvider` interface are correct as-is per the issue's own
   dependency ordering (#297 not yet merged). Confirmed by reading the
   issue body's own text ("restricted fields stripped") against
   `server.go`'s interface doc comment, which already describes exactly
   that contract for whoever implements #297.

## Alternatives

1. **Re-implement `internal/agentapi` from scratch per a fresh top-down
   design, ignoring the existing code.** Rejected: the existing
   implementation already matches the issue's endpoint list, auth model,
   envelope contract, and idempotency/durability invariants, and carries
   773+112 lines of passing tests exercising subtle correctness properties
   (redelivery idempotency, kill-switch propagation to owner-facing
   actions, job/conversation mismatch rejection, lead-only job completion)
   that a rewrite would have to re-derive from the same source material
   this investigation already read. Discarding working, tested code to
   satisfy a "design proposal" format would be pure churn and would
   introduce regression risk on invariants (e.g. `HasAgentActionForJob`'s
   409 semantics) that took real review cycles to get right (see the `P1`/
   `P2` comments throughout `server_test.go` referencing prior review
   findings).

2. **Fix the `agent.` prefix and the missing tests by editing every call
   site instead of the single `audit()` choke point.** Rejected in favor
   of the choke-point fix: `internal/agentapi/json.go`'s `audit()` is
   already the single function every handler calls, added specifically
   "so every handler logs with the same call shape" per its own doc
   comment — editing eleven call sites individually when one exists for
   this exact purpose would violate that stated intent and create a
   drift risk for the next endpoint added to this package.

3. **Move the audience-isolation test into `internal/agentapi/server_test.go`
   by wiring a real `localjwt.Provider` into `testHarness`.** Considered,
   and partially reasonable, but rejected as the primary location: the
   interesting failure mode the issue calls out is specifically about
   *routing* — a bridge token must fail at the `/bridge` vs
   `/api/agent/v1` boundary that `cmd/server/main.go` establishes, which
   `internal/agentapi` alone cannot exercise (it has no bridge routes to
   test against). A `cmd/server`-level test (or a small dedicated test file
   that constructs both provider chains) is the natural place this
   cross-package invariant lives; `internal/agentapi` can still gain a
   narrower same-package test that swaps `testHarness`'s identity-injection
   for a real provider on selected tests if the implementer finds that
   more convenient, but the cross-mount assertion belongs at the
   integration layer.

## Platform impact

- **Migrations:** none. All schema this surface reads/writes
  (`agent_profiles`, `incoming_events`, `conversations`,
  `conversation_messages`, `agent_actions`, `agent_jobs`, `job_leads`,
  `owner_notifications`) already exists per `internal/db/agent_schema.go`
  and is unaffected by the proposed changes (audit-name prefix and new
  tests touch no schema).
- **Backward compatibility:** the `agent.` audit-prefix change is
  additive-only for consumers of the audit log (existing entries keep their
  old names; only new entries get the prefix) — any downstream tooling that
  greps `LogToolCall` output for the current bare names (e.g.
  `"propose_reply"`) should be checked before merging, since `agent.`
  prefixing changes the exact string. No HTTP wire-format change: request/
  response shapes are untouched.
- **Resource impact:** negligible — one string concatenation per audit
  call; new tests run in-process against SQLite `:memory:`, no new external
  dependencies.
- **Risks + mitigations:**
  - *Risk:* the audit-prefix change breaks an existing downstream
    dashboard/alert keyed on the old bare tool names. *Mitigation:* grep
    the `deploy/` and `docs/runbooks/` trees for the current bare names
    before merging (a Tier 2 implementer step, listed in tasks.md), and
    call it out in the PR description per this repo's squash-merge
    convention so the changelog line is discoverable.
  - *Risk:* the new end-to-end audience test is flaky if it depends on
    wall-clock JWT expiry. *Mitigation:* mint tokens with a several-minute
    TTL in the test, matching the pattern already used in
    `internal/auth/localjwt/issuer_test.go`.
  - *Risk:* changing `auth.Middleware`'s status code later (if a future
    decision reverses Open Question 1) is a breaking change for any
    worker code that already treats 401 as "re-authenticate" vs 403 as
    "fatal, do not retry." *Mitigation:* this proposal explicitly does not
    make that change; it is flagged for human sign-off precisely because
    of this downstream-behavior risk.
