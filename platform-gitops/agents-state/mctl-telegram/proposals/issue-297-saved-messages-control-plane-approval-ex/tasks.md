# Tasks: issue-297-saved-messages-control-plane-approval-ex

- [ ] 1. Confirm/land `AGENT_ENABLED`, `AGENT_KILL_SWITCH`,
      `AGENT_PROFILE_PATH` in `internal/config/config.go` (reconcile with
      whatever #296 already added; add only what's missing, following the
      `envBool`/`envOr` pattern next to `AgentRetentionDays`) — DoD: `Config`
      exposes `AgentEnabled bool`, `AgentKillSwitch bool`,
      `AgentProfilePath string`; `config_test.go` covers defaults (all
      off/empty) and explicit env overrides; `.env.example` documents the
      three vars with the same comment style as `AGENT_RETENTION_DAYS`.
- [ ] 2. Add `internal/agent/policy` with `DisclosureSep` if #296 has not
      already introduced it (check at implementation time; do not duplicate)
      — DoD: single source of truth for the separator constant, imported by
      `internal/agent/executor`; if #296 already owns it, this task is a
      no-op and executor imports from there instead.
- [ ] 3. Implement `internal/agent/control.ParseCommand` (depends on 1 for
      the `AGENT_ENABLED` gate at the call site, not for the parser itself,
      which has no I/O and no dependency on config) — DoD: table-driven
      tests cover every listed verb (`status`, `leads`, `show <id>`,
      `continue <id>`, `pause`, `takeover <id>`, `approve <code>`,
      `reject <code>`), plus malformed input (missing prefix, unknown verb,
      non-numeric id, missing/empty code, extra whitespace, empty string) —
      each malformed case asserts a typed `ParseError`, not a panic or a
      silently-wrong `Command`.
- [ ] 4. Add `Store.ListAgentActionsByStatus` and a minimal
      status-summary/lead-count read helper to `internal/db` (small,
      additive; needed by `/mctl status` and by the executor's poll loop) —
      DoD: unit tests in `internal/db` following the existing
      `seedAgentUser`/`newTestStoreCrypted` fixtures; scoped by `user_id`
      exactly like every other getter in `agent_actions.go`.
- [ ] 5. Implement `internal/agent/control.Notifier`
      (`NotifyOwnerSummary`, `RequestApproval`) and the unexported
      `formatSummary`/`formatApproval` pure formatters, plus approval-code
      generation with collision retry against `idx_agent_actions_code`
      (depends on 4) — DoD: formatter unit tests assert the approval message
      always contains both `/mctl approve <code>` and `/mctl reject <code>`
      lines and the full draft text; `Notifier` tests use a fake
      `SendToSelf` (interface-seam over `internal/telegram`, see task 9) to
      verify the insert→send→mark-sent/failed sequence including the
      failure path (send error → `MarkOwnerNotificationFailed`, row stays
      queryable as `failed`, not silently dropped).
- [ ] 6. Implement `internal/agent/control.HandleCommand` for all eight
      command kinds, wired to `Store` methods only (no raw SQL) — DoD: each
      handler has a test against a real (in-memory SQLite) `Store` exercising
      the happy path and the "already resolved" / "not found" path for
      `approve`/`reject` (double-approve must be a friendly no-op reply, not
      an error); `continue`/`takeover`/`pause` assert the exact `Store`
      method and state constant used, matching `db.ConversationActive` /
      `db.ConversationTakenOver` / `SetAgentAutopilotPaused`.
- [ ] 7. Implement `internal/agent/profile.OwnerProfileProvider` (YAML
      load, mtime-checked reload, `Get`/`RestrictedFieldPolicy`) — DoD: add
      `go.yaml.in/yaml/v2` (or chosen lib) as a direct `go.mod` dependency;
      fixture-based tests assert (a) `Get()`'s returned struct has no field
      or map entry that can reach a `restricted:` YAML value even via
      reflection/JSON-marshal-and-inspect of the returned type, (b)
      `RestrictedFieldPolicy` returns the correct booleans for a known key
      and `ok=false` for an unknown one, (c) missing file / unset
      `AGENT_PROFILE_PATH` / malformed YAML all return
      `ErrProfileUnavailable`, never panic.
- [ ] 8. Define the profile YAML shape as a documented example file (e.g.
      `docs/agent-profile.example.yaml`) with identity / public_profile /
      skills / preferences / restricted sections and inline comments
      explaining `approval_required` / `never_auto_send` — DoD: the example
      file round-trips through task 7's loader in a test
      (`profile_test.go` loads the doc example, not just an ad hoc fixture,
      so the two cannot drift).
- [ ] 9. Add a small seam over `internal/telegram.SendToSelf` /
      `SendToInputPeer` usable by both the notifier and the executor without
      a live Telegram connection in unit tests (e.g. a `Sender` interface
      satisfied by a thin `pool.Borrow`-wrapping adapter in each package,
      with a fake in tests) — DoD: no new behavior in `internal/telegram`
      itself (it stays a leaf package); the seam lives in
      `internal/agent/control` and `internal/agent/executor`.
- [ ] 10. Implement `internal/agent/executor.Executor.ExecuteOne` — the
      approve→executing→executed state machine with the kill-switch /
      profile-mode / conversation-state re-checks (depends on 1, 2, 9) —
      DoD: unit tests cover: (a) happy path ends in `executed` with
      `executed_tg_message_id` set and `autonomous_turns` incremented; (b)
      kill switch flips false between claim-check and CAS — action stays
      `approved`, no send attempted; (c) `AutopilotPaused` true at
      re-check time blocks execution, action stays `approved`; (d)
      conversation state is `paused`/`taken_over`/`closed` at re-check
      time — blocked, action stays `approved`; (e) two concurrent
      `ExecuteOne` calls on the same action — exactly one sends, the other
      observes `RowsAffected()==0` and returns a no-op nil error; (f) send
      returns an error after the CAS to `executing` — action is left in
      `executing` and NOT auto-retried by a second `ExecuteOne` call on the
      same row (assert calling `ExecuteOne` again on an `executing` row is
      rejected by `allowedActionTransitions`, since `executing` has no
      outbound entry in that map); (g) disclosure line is appended with
      `DisclosureSep` before send, verified against the fake sender's
      captured text (never asserted via a real log line, to keep this
      redaction-safe by construction).
- [ ] 11. Implement `Executor.Run` poll loop and
      `sweeper.AgentApprovalExpiry` (thin wrapper over
      `Store.ExpireStaleAgentActions(ctx, 24*time.Hour)`, mirroring
      `sweeper.AgentRetention`'s shape) (depends on 10) — DoD:
      `sweeper_test.go`-style test asserts a `pending_approval` row older
      than 24h flips to `expired` and a fresh one does not; `Run` test
      asserts one poll tick processes all currently-`approved` rows and
      logs (not panics) on a per-row error without stopping the loop.
- [ ] 12. Wire `AGENT_ENABLED` gating, the executor goroutine, and the
      approval-expiry sweeper into `cmd/server/main.go` next to the existing
      `sweeper.AgentRetention` call (depends on 1, 11) — DoD:
      `main_test.go` (or a new focused test) asserts nothing starts when
      `AGENT_ENABLED` is unset/false; a smoke test with it enabled confirms
      the goroutines are launched without blocking server startup.
- [ ] 13. Audit-log coverage: ensure every Saved Messages send (summary,
      approval request, executed reply) and every `agent_actions` status
      transition emits an `slog` line with only non-sensitive attributes
      (`action_id`, `user_id`, `conversation_id`, `from`/`to` status, `kind`)
      — DoD: a redaction test in `internal/agent/...` (or extending
      `internal/audit/redact_test.go`) feeds a captured log record from each
      new code path through `RedactingHandler` and asserts no draft text,
      approval code, or restricted profile value appears in the output; if
      a new attribute key is introduced that needs redaction, add it to
      `sensitiveKeys` in `internal/audit/redact.go` in the same PR.
- [ ] 14. Update `docs/` (or `README.md`'s agent section, wherever #296
      documents the agent surface) with the `/mctl` command list and the
      approval flow — DoD: doc lists all eight commands and the 24h
      approval TTL; cross-links the example profile YAML from task 8.

## Tests

- [ ] T1. `internal/agent/control`: `ParseCommand` table-driven test, all
      eight verbs + malformed-input cases (task 3).
- [ ] T2. `internal/agent/control`: `formatApproval`/`formatSummary` pure
      formatter tests (task 5).
- [ ] T3. `internal/agent/control`: `Notifier` insert/send/mark-sent and
      insert/send-fails/mark-failed sequences against a fake sender (task 5).
- [ ] T4. `internal/agent/control`: `HandleCommand` per-verb tests against a
      real in-memory `Store`, including double-approve/double-reject no-op
      behavior (task 6).
- [ ] T5. `internal/agent/profile`: restricted-field-never-surfaced test
      (structural, via reflection/marshal of `Get()`'s return type), missing/
      malformed file handling, `RestrictedFieldPolicy` lookups (task 7).
- [ ] T6. `internal/agent/profile`: example YAML doc round-trips through the
      loader (task 8).
- [ ] T7. `internal/agent/executor`: `ExecuteOne` state-machine tests (a)-(g)
      listed in task 10, including the kill-switch-flip-mid-flow case
      explicitly called out by the issue.
- [ ] T8. `internal/agent/executor` / `internal/sweeper`: approval-TTL
      expiry sweep test and poll-loop-processes-all-approved test (task 11).
- [ ] T9. Redaction coverage test for every new log call site (task 13).
- [ ] T10. `go vet ./...`, `go fmt ./...`, `golangci-lint run` clean; `go
      test ./...` green, matching `CONTRIBUTING.md`'s pre-push checklist.

## Rollback

- All changes are additive (new packages under `internal/agent/`, new
  `internal/db` read-only helper methods, new config fields, one new
  background-loop wiring block in `main.go`). No schema migration is
  introduced, so there is nothing to reverse at the data layer.
- The primary kill mechanism is `AGENT_KILL_SWITCH=true` (or unsetting
  `AGENT_ENABLED`), which takes effect within one executor poll interval
  without a deploy — this is the intended first response to any incident,
  not a code rollback.
- If a code rollback is still needed: revert the PR(s) that add
  `internal/agent/control`, `internal/agent/executor`,
  `internal/agent/profile`, and the `main.go` wiring block. Because nothing
  else in the codebase imports these packages (the listener/API surface
  that will call into `control.HandleCommand`/`Notifier` is #296's
  responsibility and not built here), the revert is a clean removal with no
  fan-out.
- Any `agent_actions` rows already moved to `executing` at the time of a
  rollback are, by design, left exactly as they were pre-rollback (the
  no-auto-retry rule means rollback cannot make this worse) — they remain
  visible via direct DB query for manual operator resolution, same as the
  documented crash-recovery story.
- Rows already `approved` but not yet claimed simply stop being polled once
  the executor goroutine is removed/disabled; they are not lost and will
  resume executing the moment the feature is re-enabled (or can be resolved
  manually).
