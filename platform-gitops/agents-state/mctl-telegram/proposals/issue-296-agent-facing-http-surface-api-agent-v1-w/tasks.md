# Tasks: issue-296-agent-facing-http-surface-api-agent-v1-w

Context for the implementer: `internal/agentapi` and its `cmd/server`
wiring already exist and already satisfy nearly all of issue #296 — this is
not a greenfield build. Tasks 1-4 close the specific, verified gaps
documented in design.md. Task 5 is a verification-only pass to catch
anything this read-only investigation could not run (tests, lint, build).
Do not restructure working handlers/tests beyond what each task specifies.

- [ ] 1. Prefix every audit entry this package writes with `agent.` —
      DoD: `internal/agentapi/json.go`'s `audit()` method changes its
      `s.Store.LogToolCall(ctx, userID, tool, ...)` call to pass
      `"agent."+tool` instead of `tool`, with a one-line comment
      referencing the issue's `agent.<name>` requirement; no handler call
      site changes (they all already funnel through `audit()`); `go build
      ./...` passes; a new/updated test in `internal/agentapi` asserts a
      handler's persisted `LogToolCall` row (or an equivalent stored audit
      record, via whatever accessor `internal/db/audit_chain.go` /
      `store_audit_test.go` already exposes for reading back tool-call
      rows) has `tool = "agent.get_events"` (or another representative
      name), not the bare name.

- [ ] 2. Grep `deploy/`, `docs/runbooks/`, and any Grafana/alert
      definitions (`deploy/grafana`, `deploy/alerts`) for the current bare
      tool-name strings this package logs (`get_events`, `propose_reply`,
      `save_job_lead`, `complete_agent_job`, `get_policy`,
      `get_recruiter_profile`, `pause_autopilot`, `get_lead`,
      `get_conversation_context`, `get_event`, `request_owner_approval`,
      `send_owner_summary`) before merging task 1 — DoD: either no match
      found (safe to merge task 1 as-is), or matches found and updated in
      the same PR to the `agent.`-prefixed form so dashboards/alerts do not
      silently go dark.

- [ ] 3. Add an end-to-end audience-isolation test proving cross-audience
      tokens are rejected across the `/api/agent/v1` vs `/bridge`/`/mcp`
      boundary (depends on nothing above; can land independently or in the
      same PR as 1-2) — DoD: a new test (either
      `cmd/server/agentapi_audience_test.go` or an addition to
      `cmd/server/main_test.go`) that: constructs a `localjwt.Issuer` and
      two `localjwt.Provider`s with `ExpectedAudience: "bridge"` and
      `ExpectedAudience: "agent"` respectively (mirroring
      `selectBridgeProvider`/`selectAgentProvider`'s actual config, not a
      hand-rolled shortcut), mints one token per audience, and asserts:
      (a) the `aud=bridge` token against the agent-audience provider's
      `Authenticate` returns an error (and, through `auth.Middleware`,
      HTTP 401 today per requirements.md Open Question 1 — assert the
      actual current status code, do not assume 403); (b) the `aud=agent`
      token against the bridge-audience provider likewise errors/401s;
      (c) the `aud=agent` token against the agent-audience provider
      succeeds and yields the right `TelegramID`. Test passes with
      `go test ./cmd/server/...`.

- [ ] 4. Add schema-validation edge-case tests to
      `internal/agentapi/server_test.go` (independent of 1-3) — DoD: three
      new test functions: (a) `TestHandleProposeReply_RejectsUnknownField`
      — POST to `/actions/propose_reply` with a JSON body containing an
      extra field such as `"peer_tg_id"` or `"peer"` alongside valid
      `conversation_id`/`text` asserts HTTP 400 (this is also the
      concrete regression test for "no client-supplied peer is ever
      honored," satisfying that specific issue requirement); (b)
      `TestDecodeStrict_MalformedJSONReturns400` — POST a body that is not
      valid JSON (e.g. `{"conversation_id":`) to any POST endpoint asserts
      400, not 500; (c) `TestDecodeStrict_OversizedBodyReturns400` — POST a
      body larger than `maxRequestBodyBytes` (1 MiB) asserts 400, not a
      panic or a hung connection. `go test ./internal/agentapi/...` passes.

- [ ] 5. Full verification pass (depends on 1-4 landing) — DoD: `go fmt
      ./...`, `go vet ./...`, and `go test ./...` all pass locally;
      `golangci-lint run` passes if available; re-read
      `internal/agentapi/server_test.go` and `tokenhandler_test.go` in full
      (not just this investigation's excerpts) to confirm no existing
      assertion depends on the bare (unprefixed) audit tool names before
      task 1 lands; confirm `AGENT_ENABLED=false` still fully hides
      `/api/agent/v1` (no route registered, no panic) with the changes
      applied.

## Tests

- [ ] T1. `TestAgentAuditToolNamesArePrefixed` (task 1) — every handler in
      `internal/agentapi` that calls `s.audit(...)` produces a
      `LogToolCall` entry whose `tool` starts with `agent.`.
- [ ] T2. `TestAgentAudienceIsolation_BridgeTokenRejectedByAgentSurface`
      and `TestAgentAudienceIsolation_AgentTokenRejectedByBridge` (task 3)
      — the core requirement the issue names explicitly ("bridge/API
      tokens must 403 here, and agent tokens must 403 on non-agent
      routes"); document the actual observed status code if it differs
      from the issue's literal "403".
- [ ] T3. `TestHandleProposeReply_RejectsUnknownField` (task 4) — proves no
      client-supplied peer field is ever accepted, the single most
      security-relevant assertion the issue calls out by name.
- [ ] T4. `TestDecodeStrict_MalformedJSONReturns400` /
      `TestDecodeStrict_OversizedBodyReturns400` (task 4) — malformed input
      never produces a 500.
- [ ] T5. Regression run of the existing suite —
      `TestHandleEvents_TimesOutEmpty` (long-poll timeout, already passes),
      `TestHandleJobComplete_RequiresPersistedAction` /
      `_LeadOnlyJobCanComplete` (durable-completion invariant, already
      passes), `TestHandleOwnerFacing_KillSwitchBlocksNotification`
      (kill-switch propagation, already passes) — re-run after tasks 1-4 to
      confirm no regression from the audit-prefix change or new test
      helpers.

## Rollback

All proposed changes are additive or confined to a single audit-logging
call site:

- Task 1 (audit prefix) rolls back by reverting the one-line change in
  `internal/agentapi/json.go`'s `audit()` method — no data migration is
  needed either direction since `LogToolCall` rows are an append-only
  audit trail (per `internal/db/audit_chain.go`'s hash-chain design) and
  old rows with bare names remain valid, readable history regardless of
  which convention new rows use.
- Tasks 2-5 (dashboard string updates, new tests) are pure additions;
  rollback is `git revert` of the relevant commit(s) with no runtime state
  to unwind.
- No task touches `AGENT_ENABLED` gating, so if anything goes sideways
  post-merge, disabling the entire surface in production remains the
  existing, already-tested kill switch: set `AGENT_ENABLED=false` (or
  engage `AGENT_KILL_SWITCH=true` to keep the surface reachable for
  read-only polling but deny every state-changing action without a
  redeploy).
