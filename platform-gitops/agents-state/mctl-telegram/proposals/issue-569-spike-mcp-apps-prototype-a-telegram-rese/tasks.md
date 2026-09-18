# Tasks: issue-569-spike-mcp-apps-prototype-a-telegram-rese

- [ ] 1. Probe whether `mark3labs/mcp-go v1.0.0` can carry the MCP Apps contract:
      declare a resources capability, register a static resource and a resource
      template, serve a non-JSON MIME type, and attach `_meta` to a tool declaration
      and read it back over streamable HTTP — DoD: a `//go:build spike` harness proving
      or disproving each of the five, and a written verdict in
      `docs/plans/mcp-apps-spike.md` (SDK suffices / needs a scoped upstream patch,
      sketched / cannot express it, direction rejected). No UI work starts until this
      file exists. Evidence to date: `internal/mcpprobe/modern.go:14` already decodes
      `mcp.Meta`, and `go.mod` pulls `yosida95/uritemplate/v3` indirectly — suggestive,
      not proof.
- [ ] 2. Pin the exact MCP Apps resource contract from the published extension —
      URI scheme, MIME type, required `_meta` keys, how a tool advertises its UI
      (depends on 1) — DoD: contract recorded in the plan doc with a retrieval date,
      since the extension is young and moving.
- [ ] 3. Add the `TG_MCP_APPS` flag (default false) to `internal/config/config.go` and
      a `WithAppUI(bool)` builder on `*mcp.Server` alongside `WithToolFilter`
      (`internal/mcp/server.go:156`) — DoD: flag parsed and documented in
      `.env.example`; with it false, `newMCPServer` produces byte-identical
      capabilities and tool list to today, asserted by a test.
- [ ] 4. Create `internal/mcp/appui` holding only presentation: `//go:embed`-ed
      `assets/triage.html`, a `Version()` returning the SHA-256 prefix of the embedded
      bytes, and `Resource()` returning the descriptor (depends on 2, 3) — DoD: the
      package imports no `internal/telegram`, `internal/db` or `internal/auth` symbol
      (enforced by a test asserting its import set); the document is self-contained
      with no remote script, style, font or image; it carries a CSP meta at least as
      strict as `internal/oauth/local_bridge_activate_page.go:131` minus the
      `img-src https://ui.mctl.ai` allowance, plus `frame-ancestors`, which no CSP in
      this repo currently sets.
- [ ] 5. Register the resource in `newMCPServer` behind the flag, adding the repo's
      first `WithResourceCapabilities` and `AddResource` calls (depends on 3, 4) —
      DoD: flag on, `resources/list` and `resources/read` return the document; flag
      off, neither method is advertised; `cmd/mcpprobe` run against both builds and the
      diff recorded.
- [ ] 6. Build the research surface in `assets/triage.html` over `list_dialogs`,
      `get_unread_messages`, `get_messages` and `search_messages`, consuming
      `structuredContent` only (depends on 5) — DoD: unread and recent dialogs, search
      results, cards with sender/channel, timestamp, snippet and a
      canonical-peer-plus-message-id source reference, filters for
      dialog/channel/date/query, and an expandable context view; every filter
      re-invokes a tool rather than silently filtering a stale cache; pagination uses
      the tools' own `limit`/`next_before_id` (`internal/mcp/tools.go:1932`) and shows
      what was truncated. No tool signature changes.
- [ ] 7. Implement the untrusted-content renderer (depends on 6) — DoD: a single
      function strips the `<telegram-content …>` envelope added by
      `WrapUntrustedContent` (`internal/mcp/format.go:32`) and inserts the body via
      `textContent`; `innerHTML` appears nowhere in the asset (grep-asserted in a
      test); every card carries a persistent untrusted-origin marker; nothing in a
      message body can populate a tool argument, prefill a draft, or reach the host as
      a prompt without an explicit user gesture. Note for the threat model:
      `format.go:36` rewrites only the exact literal `</telegram-content>`, so case and
      whitespace variants reach the renderer intact — the renderer must not depend on
      that escape being complete.
- [ ] 8. Add `prepare_send_message`, mirroring `prepare_pin_message`
      (`internal/mcp/tools.go:568`) — DoD: requires `telegram:messages:send`, takes the
      per-peer limiter tap (`evaluateDirectSendLimiter`, `:1834`), calls
      `s.Confirms.Issue(id.UserID, "send", HashSendPayload(peer, text))` — the first
      caller of `HashSendPayload` (`internal/mcp/confirm.go:212`) — and returns
      `{confirmation_id, peer_redacted, text_preview, expires_at, would_send,
      dry_reason}` where `would_send` is `evaluateSendGate`'s verdict at prepare time.
      Declares an open output schema via `outputSchema[T]`.
- [ ] 9. Add an optional `confirmation_id` argument to `send_message` (depends on 8) —
      DoD: absent, behaviour is byte-identical to today; present, the handler runs
      `evaluateSendGate` first and then
      `s.Confirms.Consume(confID, id.UserID, HashSendPayload(peer, text))`, mapping the
      three sentinels to the same distinct messages `pin_message` uses
      (`internal/mcp/tools.go:689-693`). The argument is never required.
- [ ] 10. Satisfy the build guards for the new tool (depends on 8) — DoD: an entry in
      `docs/portal-allowlist.json` with `upstream_gates`
      `["send-gate", "telegram:messages:send"]` and a reason, applied via
      `scripts/portal-allowlist-apply.sh`; a row in the `TestToolAnnotations` table
      (`internal/mcp/annotations_test.go:14`) with `readOnly=false`,
      `destructive=false`, `openWorld=false`; `go test -race ./internal/mcp/...` green.
- [ ] 11. Build the action surface in the App (depends on 7, 9) — DoD: an editable
      draft showing the full recipient and the complete text, an attachment summary
      when the source message carries media, an explicit confirm control that calls
      `prepare_send_message` and then `send_message` with the returned id, a result
      state that distinguishes delivered from preview and shows the server's
      `dry_reason` verbatim, and the audit reference. Under
      `ToolFilter = "read-only"` (`internal/mcp/server.go:156`) the surface renders as
      unavailable, driven by what `tools/list` actually contains.
- [ ] 12. Exercise the App in Local Bridge mode (depends on 11) — DoD: research and
      draft flows work over `bridgeCall` (`internal/mcp/tools.go:113`); media uses
      `prepare_get_media`/`get_media` because `fetch_media` is refused on that path
      (`:282`); confirmed that the App cannot address a daemon the authenticated
      identity does not own, given `IsActiveDeviceForUser`
      (`internal/db/local_bridge_devices.go:219`) and the bridge handler's refusals
      (`internal/bridge/server.go:135-175`).
- [ ] 13. Run the App against the MCP Apps reference host, then Claude.ai / the Claude
      connector, then Claude Desktop or Code, then any reachable ChatGPT MCP surface
      (depends on 11) — DoD: `docs/reports/mcp-apps-host-matrix.md` with a row per host
      recording renders / tool calls from App / confirmation UX / notes, each dated,
      and an explicit "not supported as of <date>" where that is the answer.
- [ ] 14. Write `docs/reports/mcp-apps-threat-model.md` (depends on 12, 13) — DoD:
      covers iframe-to-tool invocation, untrusted Telegram content rendering, identity
      and scope handling, and confirmation binding; states residual risks including a
      host that ignores the CSP, the `format.go:36` escape gap from task 7, and the two
      OriginGuard fail-open paths (an empty allowlist disables the guard entirely,
      `internal/web/origin.go:29`; an unparseable `PUBLIC_BASE_URL` only warns,
      `internal/config/config.go:360`). Records the decision not to mint a new OAuth
      scope for the App, since it invokes only tools the caller could already invoke
      with `telegram:*` and `account:manage`.
- [ ] 15. Write the submission-positioning note and draft the amendment to
      `claude-connector-submission.md:191-194`, which currently declares no interactive
      UI components and no MCP-App widgets (depends on 13) — DoD: states what product
      capability is new versus the plain tool connector; contains an explicit sentence
      that directory acceptance is not implied; the amendment is drafted in the report
      and **not** applied to `claude-connector-submission.md`, which stays accurate for
      the shipping build.
- [ ] 16. Capture UX screenshots and a short walkthrough video against the synthetic
      fixture set, then repeat the core flow once against a throwaway non-destructive
      live account (depends on 11) — DoD: media attached to issue #569, not committed;
      each screenshot identifiable by the `appui.Version()` hash shown in the UI; no
      real account's numeric id, name or handle appears anywhere, per `.claude/CLAUDE.md`.
- [ ] 17. Close the spike with a verdict (depends on 14, 15, 16) — DoD: a dated status
      line in `docs/plans/mcp-apps-spike.md` reading validated or rejected; if
      validated, child implementation issues filed covering at minimum productionising
      `appui`, making `confirmation_id` required on `send_message`, and the connector
      re-submission; if rejected, the evidence that settled it, written down.

## Tests

- [ ] T1. `TestAppUIDisabledByDefault` — with `TG_MCP_APPS` unset, the initialize
      response advertises no resources capability and the tool list and every input and
      output schema match a golden snapshot of the current build.
- [ ] T2. `TestAppUIResourceIsSelfContained` — the embedded HTML contains no `http://`
      or `https://` subresource reference, no `<script src=`, and no `innerHTML`;
      asserted by scanning the embedded bytes, in the style of
      `internal/web/security_test.go`.
- [ ] T3. `TestAppUIPackageImports` — `internal/mcp/appui` imports no Telegram,
      database or auth package, so the UI layer provably holds no credential path.
- [ ] T4. `TestPrepareSendMessageBindsPayload` — prepare then send with identical
      arguments succeeds; send with altered `text` fails `ErrConfirmationMismatch`;
      send with altered `peer` fails the same way; nothing is delivered on either
      failure.
- [ ] T5. `TestSendConfirmationIsIdentityBound` — a confirmation issued for user A and
      presented by user B fails `ErrConfirmationWrongUser` and leaks no state of A's
      pending action.
- [ ] T6. `TestSendConfirmationExpires` — past `ConfirmationTTL`
      (`internal/mcp/confirm.go:15`) the id is indistinguishable from unknown, using
      the store's overridable `now` hook.
- [ ] T7. `TestSendConfirmationIsSingleShot` — replaying an accepted id fails, and a
      dry-run send does not burn the confirmation.
- [ ] T8. `TestAppSendStillHonoursWriteGate` — with `ALLOW_SEND=false`, with the
      `telegram:messages:send` scope absent, with per-account `send_enabled=false`, and
      for the demo reviewer identity, a send carrying a valid `confirmation_id` still
      returns `sent=false` with the matching `dry_reason`
      (`internal/mcp/tools.go:1794-1832`).
- [ ] T9. `TestAppCannotReachUnscopedTools` — an App-shaped call naming
      `set_telegram_access`, `mint_worker_token` or `set_account_send` with only read
      scopes is refused with the identical `requireScope` error a chat call receives.
- [ ] T10. `TestSendMessageUnchangedWithoutConfirmationID` — omitting the new argument
      reproduces today's request and response bytes exactly.
- [ ] T11. `TestUntrustedRenderStripsEnvelope` — adversarial synthetic fixtures using
      `Alice`/`Bob`/`Carol`/`Dana` covering a forged `</telegram-content>`, its case
      and whitespace variants, `<script>`, `<img onerror=>`, an iframe-escape attempt,
      and prompt-injection prose: each renders as inert text, and none produces a tool
      argument or a prefilled draft. Modelled on
      `internal/agent/policy/adversarial_output_test.go`.
- [ ] T12. `TestPortalAllowlistCoversNewTool` — the existing
      `internal/mcp/portal_allowlist_test.go` passes with the
      `prepare_send_message` entry, confirming the derived gate set matches the handler.
- [ ] T13. `TestOutputSchemasStayOpenToAdditiveFields` — the existing guard
      (`internal/mcp/output_schema_open_test.go`) passes for the new result struct.
- [ ] T14. End-to-end over `httptest` in the style of
      `internal/mcp/zero_admin_e2e_test.go`: authenticate, read the App resource, run a
      search, prepare a send, tamper with the text, observe the refusal, then send the
      untampered payload and observe the dry-run preview.
- [ ] T15. Full suite as CI runs it — `go vet ./...`, `go build ./...`,
      `go test -race ./...` (`.github/workflows/build.yml`) — green with the flag both
      on and off.

## Rollback

The prototype is off by default, so the ordinary rollback is to leave
`TG_MCP_APPS` unset: `newMCPServer` then declares no resources capability, registers
no resource, and the App is unreachable. Nothing else in the request path changes.

If the App must be withdrawn from an environment where it was enabled, unset the flag
and restart. Confirmations are in-memory and short-lived
(`internal/mcp/confirm.go:20`), so any in-flight drafts simply expire; no state is
stranded and no data is lost.

If `prepare_send_message` itself must be withdrawn, revert the registration in
`newMCPServer`, the `internal/mcp/tools.go` builder, its
`docs/portal-allowlist.json` entry and its `TestToolAnnotations` row together — those
four move as one unit or CI fails. Reverting the optional `confirmation_id` argument
on `send_message` is safe in isolation because no caller is required to supply it and
no persisted state references it.

There is no migration, so there is nothing to reverse in the database. The audit chain
is unaffected: App-initiated calls write the same rows through the same
`s.audit`/`LogToolCall` path (`internal/mcp/tools.go:2190`,
`internal/db/store.go:1499`), and removing the App does not invalidate them.

If the spike is rejected outright, delete `internal/mcp/appui`, the flag and the
`prepare_send_message` change, and keep `docs/plans/mcp-apps-spike.md` and the two
reports — the evidence is the point of the exercise and outlives the code.
