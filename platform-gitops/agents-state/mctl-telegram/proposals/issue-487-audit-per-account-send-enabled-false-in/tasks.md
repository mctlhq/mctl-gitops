# Tasks: issue-487-audit-per-account-send-enabled-false-in

- [ ] 1. Add the operator audit queries to `docs/runbook.md`, in a new
      section near the existing `telegram_accounts` / `audit_logs` queries
      (around the Local Bridge diagnostics section). Include: (a) the
      disabled-but-active account list, (b) the join against
      `audit_logs.tool_name = 'send_message:draft'` with an adjustable time
      window, and (c) a short interpretation note explaining that
      `send_enabled=false` is the default state (not evidence of
      revocation) per the corrected issue text — DoD: the section renders
      correctly in Markdown, the SQL is valid Postgres (matching the
      production schema in `internal/db/db.go`), and it explicitly notes the
      window is adjustable and the query targets Postgres/production, not
      the SQLite dev schema.

- [ ] 2. Extract the per-account-disabled message in
      `internal/mcp/tools.go`'s `evaluateSendGateAccountFlag` (currently the
      inline literal `"per-account send_enabled=false — contact the
      operator to enable real sends for your account"`) into a package-level
      `const reasonSendDisabled = "..."` and return that constant instead of
      the literal — DoD: `evaluateSendGateAccountFlag`'s existing tests
      (`internal/mcp/send_message_test.go`,
      `internal/mcp/send_status_test.go`) still pass unmodified, since the
      returned string value is identical, only its source changed.

- [ ] 3. Add `Hint string `json:"hint,omitempty"`` to `telegram.SendResult`
      (`internal/telegram/send.go:15-28`) (depends on 2) — DoD: `go vet`
      and existing tests in `internal/telegram/send_test.go` pass with the
      new optional field; no existing test asserts on the full JSON shape of
      `SendResult` in a way that a new `omitempty` field would break (verify
      by running the package's tests before and after).

- [ ] 4. In `toolSendMessage`'s dry-run branch (`internal/mcp/tools.go`,
      after the `telegram.SendMessage(ctx, nil, peer, text, false,
      dryReason, nil, 0)` call around line 399), compare `dryReason` against
      `reasonSendDisabled` and, on exact match, set
      `result.Hint = "Your account has never opted into real sends. Turn it
      on from /manage, or call get_my_send_status to confirm this is the
      reason."` on the returned `*telegram.SendResult` before it is
      marshalled by `jsonResult` (depends on 2, 3) — DoD: for the other three
      dry-run causes (`ALLOW_SEND=false`, missing
      `telegram:messages:send` scope, reviewer/demo account), `Hint` stays
      empty; verified by test T2 below.

- [ ] 5. Update `send_message`'s tool description in `internal/mcp/tools.go`
      (the `mcplib.WithDescription` block starting at line 354) to mention
      the new optional `hint` field in the dry-run result, so MCP clients
      introspecting the tool description learn about it without reading
      source (depends on 3, 4) — DoD: description text mentions `hint` and
      stays consistent with `get_my_send_status`'s existing description
      style (plain language, one added sentence, no schema dump).

## Tests

- [ ] T1. Unit test in `internal/mcp` asserting
      `evaluateSendGateAccountFlag(false)`'s reason string equals the
      `reasonSendDisabled` constant, so the gate message and the hint
      comparison cannot silently drift apart (covers design.md's
      "hint text drifts from reasonSendDisabled" risk).
- [ ] T2. Table test in `internal/mcp/send_message_test.go` (extending the
      existing dry-run test cases) covering all four dry-run causes —
      reviewer/demo account, `ALLOW_SEND=false`, missing
      `telegram:messages:send` scope, and `send_enabled=false` — asserting
      `SendResult.Hint` is empty for the first three and equals the expected
      nudge text only for the fourth.
- [ ] T3. Regression test confirming a real send (gate fully open) still
      returns `Hint == ""` and `Sent == true`, so the additive field cannot
      be mistaken for a signal that always fires.
- [ ] T4. Regression test confirming `send_message:draft` is still recorded
      via `s.audit(...)` exactly as before (same tool_name, same call site)
      when the new hint logic runs, so the runbook's audit-log-based query
      (task 1) keeps working against unchanged audit data.
- [ ] T5. Manual/operator-run: execute the two runbook queries from task 1
      against a scratch/staging Postgres instance seeded with a
      `send_enabled=false`, active-session row and a matching
      `send_message:draft` audit row, and confirm both queries return that
      row — validates the SQL before it is trusted against production.

## Rollback

- Tasks 2-5 are a single small, additive code change confined to
  `internal/mcp/tools.go` and `internal/telegram/send.go`. If the nudge
  text turns out to be wrong, confusing, or mismatched to
  `get_my_send_status`'s guidance, revert the commit(s) for tasks 2-5 (or
  drop the `Hint` assignment in task 4 back to a no-op) — the gate functions
  and the audited `send_message:draft` action are untouched, so rollback
  carries no data-migration or gate-behavior risk; the field simply stops
  appearing in future responses.
- Task 1 (runbook documentation) has no runtime effect and needs no
  rollback beyond a normal doc revert if the query text is later found to be
  wrong or misleading.
