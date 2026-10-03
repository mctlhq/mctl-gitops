# Tasks: issue-569-spike-mcp-apps-prototype-a-telegram-rese

All tasks are completable inside one PR against `mctlhq/mctl-telegram`. No
sibling repository is touched, no post-merge production action is required,
and no step needs a human to click anything.

- [ ] 1. Add the `MCP_APPS_ENABLED` feature flag — DoD: `internal/config/config.go`
  gains `AppsEnabled bool` read via `envBool("MCP_APPS_ENABLED", false)` with a
  doc comment in the style of `AgentEnabled`; `.env.example` documents it next
  to `AGENT_ENABLED`; `internal/config/config_test.go` asserts the default is
  `false` and that `"true"` flips it.

- [ ] 2. Create `internal/mcpui` with the embedded App document (depends on 1) —
  DoD: new package containing `triage.html` and `app.go`. `app.go` exports
  `ExtensionID = "io.modelcontextprotocol/ui"`,
  `ResourceURI = "ui://mctl-telegram/triage"`,
  `MIMEType = "text/html;profile=mcp-app"`, `Version` (the build version
  string), `Resource() mcplib.Resource`, `Contents(uri string) []mcplib.ResourceContents`,
  `ExtensionCapability() map[string]any` and `ToolMeta() map[string]any`.
  `triage.html` is `//go:embed`ed into a `string` (matching
  `internal/ui/chrome.go:24-34`). `Resource().Meta` and the returned
  `TextResourceContents.Meta` carry `ui.csp` with empty `connectDomains`,
  `resourceDomains`, `frameDomains`, `baseUriDomains`. `ToolMeta()` emits the
  nested `{"ui": {"resourceUri": …, "visibility": ["model","app"]}}` form only,
  with a comment stating that `visibility` is a host hint and never server
  authorization. `go vet ./...` clean.

- [ ] 3. Build the research/triage UI in `triage.html` (depends on 2) — DoD: one
  self-contained document, no external origin of any kind. It performs the
  `ui/initialize` handshake, sends `ui/notifications/initialized`, and drives
  the flow through host `tools/call` requests to `get_unread_messages`,
  `list_dialogs`, `search_messages`, `get_messages` and `prepare_get_media`.
  Renders dialog/result cards with sender, channel, timestamp, snippet and
  source message reference; filters for dialog/channel/date/query; an
  expandable message-context view. Every Telegram-derived string reaches the
  DOM through `document.createElement` + `textContent`. Contains no
  `innerHTML`, `insertAdjacentHTML`, `outerHTML`, `document.write`, `eval(`,
  `new Function`, `fetch(`, `XMLHttpRequest`, `import(`, `http://` or
  `https://`. Handles `ui/notifications/tool-result` and
  `ui/notifications/size-changed`; never calls `ui/update-model-context` or
  `ui/message` with Telegram text.

- [ ] 4. Unwrap the untrusted-content envelope for display (depends on 3) — DoD:
  the App strips the exact literal envelope `internal/mcp/format.go:33`
  produces (`<telegram-content origin="telegram" peer="…" untrusted="true">` …
  `</telegram-content>`) by strict prefix/suffix match, not by regex over
  arbitrary markup and not by HTML parsing; a non-matching string is rendered
  verbatim as text; every card keeps a visible "untrusted · Telegram" marker
  regardless.

- [ ] 5. Wire the extension, resource capability and resource handler (depends
  on 2) — DoD: `internal/mcp/server.go` gains `AppsEnabled bool` and
  `WithAppsEnabled(bool) *Server` following the `WithToolFilter` shape;
  `newMCPServer` appends `mcpserver.WithResourceCapabilities(false, false)` and
  `mcpserver.WithExtensions(mcpui.ExtensionCapability())` and calls
  `srv.AddResource(mcpui.Resource(), handler)` only when `s.AppsEnabled`. The
  handler refuses with an error when `auth.From(ctx) == nil`, so an
  `AUTH_REQUIRED=false` deployment still does not serve the App body
  anonymously. `cmd/server/main.go` adds `.WithAppsEnabled(cfg.AppsEnabled)` to
  the existing option chain and logs the resolved value at startup.

- [ ] 6. Attach `_meta.ui` to the App's tools (depends on 2, 5) — DoD:
  `internal/mcp/apps.go` defines `withUIResource() mcplib.ToolOption` setting
  `t.Meta` from `mcpui.ToolMeta()` while preserving existing
  `AdditionalFields`; it is applied, only when `AppsEnabled`, to `list_dialogs`,
  `get_unread_messages`, `get_messages`, `search_messages`,
  `prepare_get_media`, `prepare_send_message` and `send_message`. With the flag
  off, no tool carries `_meta`.

- [ ] 7. Add `prepare_send_message` (depends on 5) — DoD: `toolPrepareSendMessage()`
  in `internal/mcp/apps.go`, modelled on `toolPreparePinMessage`
  (`tools.go:568`), registered through `s.addTool` only when `AppsEnabled`.
  Required `peer` and `text`; `ReadOnlyHint=false`, `DestructiveHint=false`,
  `OpenWorldHint=false`; declares its output via `outputSchema[T]()`. Makes no
  Telegram API call. Returns `{confirmation_id, peer_redacted, text,
  text_sha256, will_really_send, dry_reason, expires_at}`, where the verdict
  comes from `evaluateSendGate(ctx, s.Store, id, s.AllowSend, s.DemoReviewerTGID)`
  and `confirmation_id` from `s.Confirms.Issue(id.UserID, "send",
  HashSendPayload(peer, text))`. `peer_redacted` uses `telegram.RedactPeer`.

- [ ] 8. Bind `send_message` to an optional confirmation (depends on 7) — DoD:
  `toolSendMessage` accepts an optional `confirmation_id` string. When
  non-empty, the handler calls `s.Confirms.Consume(confID, id.UserID,
  HashSendPayload(peer, text))` **before** `evaluateSendGate` and maps
  `ErrConfirmationNotFound` / `ErrConfirmationMismatch` /
  `ErrConfirmationWrongUser` to distinct refusal messages in the style of
  `media_tools.go:207-213`. When empty, the handler's behaviour is unchanged.
  The tool description documents the argument as optional and states that the
  send gate remains authoritative either way.

- [ ] 9. Add the draft/confirm/send affordance to the App (depends on 3, 7, 8) —
  DoD: from a result card the App opens an editable draft showing the visible
  recipient, the complete text, an attachment summary when present, and the
  `will_really_send` / `dry_reason` verdict from `prepare_send_message` plus
  the `text_sha256` binding. An explicit "send" control calls `send_message`
  with the `confirmation_id`. The result view distinguishes a real send from a
  dry-run preview using the `sent` field and shows the audit reference. If
  `prepare_send_message` is absent from `tools/list` (i.e.
  `MCP_TOOL_FILTER=read-only`), the draft affordance is hidden rather than
  producing a failing call.

- [ ] 10. Record the new tool in the portal allowlist (depends on 7) — DoD:
  `docs/portal-allowlist.json` gains a `prepare_send_message` entry with
  `enabled: false` and a `reason` explaining that it is a flag-gated prototype
  affordance that should not appear on the shared Cloudflare portal surface;
  `internal/mcp/portal_allowlist_test.go` is updated to construct its server
  with `AppsEnabled=true` so the AST-derived guard keeps covering the full
  registered set instead of silently skipping the new tool. `go test
  ./internal/mcp/...` passes.

- [ ] 11. Extend the conformance probe (depends on 5, 6) — DoD:
  `internal/mcpprobe/apps.go` plus report fields in `report.go` record, for a
  given endpoint: whether `initialize` advertises
  `capabilities.extensions["io.modelcontextprotocol/ui"]` with `mimeTypes`
  containing `text/html;profile=mcp-app`; whether `resources/list` contains a
  `ui://` URI with that mimeType; whether `resources/read` returns non-empty
  inline `text`; and which tools carry a nested `_meta.ui.resourceUri`. Wired
  into `Run` (`run.go:14`) and surfaced by `cmd/mcpprobe`, following the
  existing `Outcome`/`Reason`/`Step` vocabulary. The probe is additive: it
  reports "not advertised" rather than failing against a flag-off endpoint.

- [ ] 12. Write the technical report (depends on 1-11) — DoD:
  `docs/reports/mcp-apps-spike.md` exists and contains: (a) the host
  compatibility matrix, with the reference-host row filled from an actual
  `mcpprobe` run against a locally started flag-on server and pasted verbatim,
  and the Claude.ai / Claude Desktop / ChatGPT rows marked "not measured here
  — owned by mctlhq/mctl-telegram#650" rather than guessed; (b) the
  implementation-path decision with the mcp-go v1.0.0 symbol table
  (`server.WithExtensions` `server/server.go:675`, `MCPServer.AddResource`
  `server/server.go:797`, `WithResourceCapabilities` `server/server.go:344`,
  `mcp.Tool.Meta` `mcp/tools.go:657`, `mcp.TextResourceContents.Meta`
  `mcp/types.go:956`) and the reasons the Node-sidecar, static-origin and
  SDK-fork options were dropped; (c) the threat model covering iframe → tool
  invocation, untrusted Telegram content, identity, scopes and confirmations,
  stating explicitly that `_meta.ui.visibility` is a host hint and never
  server authorization; (d) the hosting/asset decision (inline
  `resources/read`, no new HTTP route, `_meta.ui.csp` with no allowed domains,
  stable URI plus content hash); (e) the long-running-research assessment
  naming which flows approach the existing caps and deferring any job
  mechanism to `mctlhq/.github#41`, noting that `mcp/tasks.go` and
  `server/task_*.go` already exist in the pinned SDK; (f) a
  submission-positioning note describing what capability is new relative to a
  plain tool connector, recording that
  `claude-connector-submission.md:193` ("no MCP-App widgets") becomes stale
  once a deployment enables the flag and that updating it belongs to #650, and
  stating plainly that none of this predicts directory acceptance; (g) a
  readiness checklist and the proposed child implementation issues, written as
  a list in the report rather than filed from this PR.

- [ ] 13. Documentation pass (depends on 12) — DoD: `README.md` and `AGENTS.md`
  / `.claude/CLAUDE.md` key-paths lists mention `internal/mcpui` and the
  `MCP_APPS_ENABLED` flag in one line each; `docs/reports/mcp-apps-spike.md` is
  linked from wherever `docs/reports/communication-agent-c1.md` is referenced.
  No emoji, English only, conventional-commit messages.

## Tests

- [ ] T1. `internal/mcp` — flag-off surface is unchanged: with `AppsEnabled`
  false, the `initialize` result advertises no `extensions` and no `resources`
  capability, `resources/list` is unavailable, and no registered tool carries a
  non-nil `Meta`.
- [ ] T2. `internal/mcp` — flag-on surface is spec-shaped: `extensions`
  contains `io.modelcontextprotocol/ui` with `mimeTypes:
  ["text/html;profile=mcp-app"]`; `resources/list` contains
  `ui://mctl-telegram/triage` with that exact mimeType; `resources/read`
  returns one non-empty `TextResourceContents` whose `_meta.ui.csp` lists no
  domains; the seven designated tools carry nested `_meta.ui.resourceUri` and
  the deprecated flat `ui/resourceUri` key appears nowhere.
- [ ] T3. `internal/mcp` — the resource handler refuses when `auth.From(ctx)`
  is nil.
- [ ] T4. `internal/mcpui` — asset hygiene, mirroring
  `TestLiteChromeHasNoExternalDeps` (`internal/ui/chrome_test.go:76`): the
  embedded document contains none of `innerHTML`, `insertAdjacentHTML`,
  `outerHTML`, `document.write`, `eval(`, `new Function`, `fetch(`,
  `XMLHttpRequest`, `import(`, `http://`, `https://`, `fonts.googleapis.com`.
- [ ] T5. `internal/mcpui` — content-hash golden test: the sha256 of the
  embedded document matches a recorded constant, so an asset edit is a
  deliberate, reviewable change rather than silent drift.
- [ ] T6. `internal/mcp` — `prepare_send_message` issues a confirmation bound
  to `HashSendPayload(peer, text)`, makes no Telegram call, and reports
  `will_really_send=false` with the right `dry_reason` for each of the four
  gate conjuncts (demo reviewer, `ALLOW_SEND=false`, missing
  `telegram:messages:send`, `send_enabled=false`).
- [ ] T7. `internal/mcp` — confirmation binding on `send_message`: a matching
  `(peer, text)` consumes cleanly; a changed `text` yields the
  `ErrConfirmationMismatch` refusal; a second use of the same id yields the
  `ErrConfirmationNotFound` refusal; an id issued to another `UserID` yields the
  `ErrConfirmationWrongUser` refusal; and each refusal makes no Telegram call.
- [ ] T8. `internal/mcp` — back-compat: `send_message` without
  `confirmation_id` behaves exactly as before, asserted against the existing
  `send_message_test.go` expectations.
- [ ] T9. `internal/mcp` — adversarial "UI cannot bypass the gate": with
  `send_enabled=false` and a valid confirmation, a send returns `sent=false`
  with a `dry_reason`, records `send_message:draft` in the audit, and issues no
  MTProto call; and with the gate open the per-peer limiter is still debited.
- [ ] T10. `internal/mcp` — tool-filter interaction: with
  `MCP_TOOL_FILTER=read-only` and `AppsEnabled=true`, `prepare_send_message`
  and `send_message` are absent from the registered set while the App resource
  and the read tools' `_meta.ui` remain present.
- [ ] T11. `internal/mcp` — `portal_allowlist_test.go` passes with the flag-on
  tool set and fails if the `prepare_send_message` entry is removed.
- [ ] T12. `internal/mcpprobe` — the Apps probe reports "advertised" against an
  in-process flag-on server (reuse the existing `inprocess_test.go` fixture
  pattern) and "not advertised" against a flag-off one, without erroring.
- [ ] T13. `internal/config` — `MCP_APPS_ENABLED` defaults to false and parses
  `"true"`.
- [ ] T14. Repo-wide: `go fmt ./...`, `go vet ./...`, `golangci-lint run`, and
  `go test ./...` clean. Any fixture uses a synthetic Telegram identifier and
  one of the existing `Alice` / `Bob` / `Carol` / `Dana` personas, with
  `git grep <id>` run before picking a numeric id.

## Rollback

Three levels, cheapest first.

1. **Operator, no deploy of this repo.** Unset or set
   `MCP_APPS_ENABLED=false`. The server stops advertising the extension and the
   resource capability, unregisters nothing else, drops `_meta.ui` from every
   tool, and `prepare_send_message` disappears from `tools/list`. The
   `initialize` and `tools/list` responses return to exactly what production
   serves today. T1 is the test that guarantees this is a real rollback and not
   a partial one. Since the flag is set nowhere in this PR, this is also the
   state the PR ships in.

2. **Partial revert.** Drop commit(s) for tasks 2-6 and 9 (the App surface)
   while keeping tasks 7-8. `prepare_send_message` plus the optional
   `confirmation_id` on `send_message` are independently useful exact-payload
   binding and are backward compatible on their own; only the
   `docs/portal-allowlist.json` entry from task 10 must stay with them.

3. **Full revert.** `git revert` the merge commit. Nothing persists outside the
   binary: no migration, no schema change, no new table or column, no new HTTP
   route, no external asset, no GitOps change, and no state in the database.
   The only in-memory addition is `ConfirmStore` entries, which are already
   single-shot and expire in 10 minutes.

No rollback step requires coordination with another repository. If the App is
found to misbehave in a host after a future deployment enables it, level 1 is
sufficient and takes effect on the next `initialize`.
