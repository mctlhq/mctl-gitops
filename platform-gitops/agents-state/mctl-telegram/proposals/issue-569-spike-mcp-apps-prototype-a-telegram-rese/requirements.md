# Spike: MCP Apps prototype for a Telegram research and triage surface

## Context

Issue #569 asks for a time-boxed spike answering two separable questions. First, a
technical one: can `tg.mctl.ai` — a Go MCP server built on `mark3labs/mcp-go v1.0.0`
and `mcpserver.NewStreamableHTTPServer` (`internal/mcp/server.go:178`) — expose a
standards-compliant MCP App, given that the server today declares only
`mcpserver.WithToolCapabilities(true)` (`internal/mcp/server.go:206`) and registers
no MCP resources at all? A repository-wide grep for `AddResource`,
`ResourceTemplate` and `mcplib.Resource` returns no non-test hit, so the resource
half of the protocol is entirely unimplemented here. Second, a product one: does a
Telegram research/triage App justify a new Claude connector submission on top of the
existing 30-tool surface, without weakening the server-authoritative safety model
(`evaluateWriteGate` at `internal/mcp/tools.go:1767`, `ConfirmStore` in
`internal/mcp/confirm.go`, `OriginGuard` at `internal/web/origin.go:22`)?

This matters because the server already has most of the ingredients an App needs and
none of the delivery mechanism. Every read tool already returns machine-readable
`structuredContent` through `jsonResult` (`internal/mcp/tools.go:2180`) against an
additive-open output schema (`outputSchema[T]` at `internal/mcp/output_schema.go:33`),
which is exactly the data contract a UI would consume — so an App can be built with
no new Telegram data path. Conversely the write path has a gap the App makes visible:
`HashSendPayload` (`internal/mcp/confirm.go:212`) exists but has no caller, because
`send_message` takes only `peer` and `text` and relies on draft-by-default plus the
host's own confirmation UI rather than an exact-payload binding of the kind
`prepare_pin_message`/`pin_message` already use (`internal/mcp/tools.go:611`,
`:686`). An iframe button click must not be allowed to stand in for that binding.
The spike therefore has to close that gap before it can honestly demonstrate a safe
action surface. This proposal covers the spike only: a flag-gated prototype, a host
compatibility report, a threat model and an implementation-path decision — not a
production connector submission.

## User stories

- AS a Telegram power user I WANT to open a research and triage view inside my MCP
  host SO THAT I can scan unread dialogs, search history and read message context
  without asking the assistant to re-narrate JSON at me.
- AS the same user I WANT to draft a reply inside that view and see the exact
  recipient and exact text that will be delivered SO THAT I can approve a
  consequential action with full knowledge of its payload.
- AS the same user I WANT the App to be unable to send anything the existing server
  gates would have refused SO THAT adopting a richer UI does not quietly lower my
  safety floor.
- AS a maintainer of `mctl-telegram` I WANT a written decision on whether
  `mark3labs/mcp-go v1.0.0` can carry MCP Apps metadata and resources SO THAT we
  either adopt it, contribute upstream, or reject the direction on evidence instead
  of on guesswork.
- AS a maintainer I WANT a recorded host support matrix covering the MCP Apps
  reference host and Claude surfaces SO THAT we do not build a UI that no host we
  care about can render.
- AS a security reviewer I WANT a threat model for the iframe-to-tool path, for
  untrusted Telegram content rendered as HTML, and for identity/scope handling SO
  THAT the App is reviewable against the guarantees `SECURITY.md` already makes.
- AS an operator I WANT the whole prototype behind a default-off flag SO THAT a spike
  cannot change the protocol surface that production clients and the Cloudflare MCP
  portal already depend on.

## Acceptance criteria (EARS)

### Extension surface

- WHEN the MCP Apps prototype flag is disabled THE SYSTEM SHALL advertise exactly the
  capabilities and tool set it advertises today, declaring no resource capability and
  registering no `ui://` resource.
- WHEN the MCP Apps prototype flag is enabled THE SYSTEM SHALL additionally declare a
  resources capability and serve at least one MCP App UI resource describing the
  Telegram research and triage surface.
- WHEN a host reads the App UI resource THE SYSTEM SHALL return a self-contained HTML
  document with no external script, style, font or image reference.
- WHILE the prototype flag is enabled THE SYSTEM SHALL keep every existing tool name,
  input schema and output schema byte-identical to the flag-disabled build, so that a
  client caching `tools/list` observes no change.
- IF `mark3labs/mcp-go v1.0.0` cannot express the App metadata the extension requires
  — resource registration, the App resource MIME type, or tool-level `_meta`
  passthrough — THEN THE SYSTEM SHALL record the precise missing capability in the
  implementation-path decision rather than silently shipping a partial surface.

### Research surface

- WHEN the App requests dialog, unread, history or search data THE SYSTEM SHALL serve
  it exclusively through the already-registered `list_dialogs`,
  `get_unread_messages`, `get_messages`, `search_messages`, `prepare_get_media` and
  `get_media` tools.
- WHILE the App is rendering THE SYSTEM SHALL require it to consume the
  `structuredContent` those tools already return, and SHALL NOT introduce a parallel
  JSON shape, a second Telegram client, or any MTProto credential inside the UI
  layer.
- WHEN the App renders a result card THE SYSTEM SHALL present sender or channel,
  timestamp, a text snippet and a stable source reference (canonical peer id plus
  message id) sufficient to reopen that message in context.
- WHEN the user applies a dialog, channel, date or query filter THE SYSTEM SHALL
  satisfy it by re-invoking the corresponding tool with the matching arguments, not
  by filtering a stale client-side cache without saying so.
- WHEN the account is in Local Bridge mode THE SYSTEM SHALL keep the research surface
  functional over the bridge path (`bridgeCall`, `internal/mcp/tools.go:113`), and
  SHALL fall back to `prepare_get_media`/`get_media` for media rather than
  `fetch_media`, which that path refuses (`internal/mcp/tools.go:282`).
- IF a research query would exceed a single synchronous tool call's practical budget
  THEN THE SYSTEM SHALL paginate through the tools' existing `limit` arguments and
  show the user what was truncated, and SHALL NOT introduce an App-specific job
  polling mechanism.

### Untrusted content

- WHEN the App renders any Telegram-origin string THE SYSTEM SHALL insert it as text,
  never as parsed markup, so that no message body can execute script or alter the
  document structure.
- WHILE rendering message bodies THE SYSTEM SHALL strip the
  `<telegram-content origin="telegram" ... untrusted="true">` envelope that
  `WrapUntrustedContent` (`internal/mcp/format.go:32`) adds to `Message.Text`, and
  SHALL display the unwrapped body with a persistent visual marker that it is
  untrusted third-party content.
- WHILE rendering THE SYSTEM SHALL rely on the existing `internal/sanitize` helpers
  as the single sanitization source and SHALL NOT introduce a second, weaker
  client-side cleaning path that could diverge from them.
- IF a message body contains text shaped like host or tool instructions THEN THE
  SYSTEM SHALL keep it inert: it must not be forwarded to the host as a prompt, must
  not populate a tool argument without an explicit user gesture, and must not
  pre-fill a draft that could be sent without the user reading it.
- WHEN a Telegram service message carries a login code or login IP THE SYSTEM SHALL
  display it already redacted by `sanitize.SensitiveTelegramContent`
  (`internal/sanitize/sanitize.go:85`), because the App reads the same tool output.

### Identity, scopes and the action surface

- WHILE any App-initiated tool call is executing THE SYSTEM SHALL derive the caller
  identity solely from the authenticated MCP request context via `auth.From(ctx)`
  (`internal/auth/identity.go:71`) and SHALL ignore any identity, user id or scope
  asserted by the UI.
- WHEN the App triggers a tool THE SYSTEM SHALL apply the same `requireScope` /
  `requireAnyScope` checks (`internal/mcp/tools.go:1849`, `:1872`) that apply to a
  chat-initiated call, with no App-specific exemption.
- IF the UI names a tool the caller's scopes do not permit — including any admin tool
  such as `set_telegram_access` or `mint_worker_token` — THEN THE SYSTEM SHALL refuse
  it with the identical error a non-App caller receives.
- WHEN the deployment runs with `ToolFilter = "read-only"`
  (`internal/mcp/server.go:156`) THE SYSTEM SHALL render the App's research surface
  normally and SHALL present the action surface as unavailable rather than offering a
  control that cannot succeed.
- WHEN the user submits a draft from the App THE SYSTEM SHALL route it through a
  prepare step that snapshots the exact `(peer, text)` pair as a payload hash using
  the existing `HashSendPayload` (`internal/mcp/confirm.go:212`) and returns a
  single-shot confirmation id bound to the caller's `UserID`.
- WHEN the corresponding send is invoked with that confirmation id THE SYSTEM SHALL
  deliver the message only if `ConfirmStore.Consume` (`internal/mcp/confirm.go:87`)
  accepts the id for this identity and for a payload hash matching the arguments
  actually supplied.
- IF the text or recipient changed between prepare and send THEN THE SYSTEM SHALL
  refuse with `ErrConfirmationMismatch` and SHALL NOT deliver anything.
- IF a confirmation id belonging to another identity is presented THEN THE SYSTEM
  SHALL refuse with `ErrConfirmationWrongUser` and SHALL NOT reveal any state of that
  other user's pending action.
- WHILE a confirmation id is older than `ConfirmationTTL`
  (`internal/mcp/confirm.go:15`) THE SYSTEM SHALL treat it as not found.
- WHEN a send is attempted THE SYSTEM SHALL apply `evaluateSendGate`
  (`internal/mcp/tools.go:1763`) unchanged, so that `ALLOW_SEND=false`, a missing
  `telegram:messages:send` scope, per-account `send_enabled=false`, or the demo
  reviewer identity each still force a dry-run preview.
- WHEN a send is forced to dry run THE SYSTEM SHALL show the user an unambiguous
  preview state carrying the server's `dry_reason`, visually distinct from a
  delivered message, and SHALL NOT let the UI present a preview as sent.
- WHILE sends are being issued THE SYSTEM SHALL continue to debit the per-peer
  limiter (`evaluateDirectSendLimiterN`, `internal/mcp/tools.go:1842`) and SHALL
  surface the refusal text to the user when the cap is reached.
- WHEN any App-initiated tool call completes THE SYSTEM SHALL write the same audit
  row `s.audit` (`internal/mcp/tools.go:2190`) writes for a chat-initiated call, and
  the App SHALL show the user the resulting outcome reference.
- WHILE the account is in Local Bridge mode THE SYSTEM SHALL keep device ownership
  enforcement on the server and bridge, and SHALL NOT let the App address a daemon
  the authenticated identity does not own.

### Hosting, transport and the existing guards

- WHILE the App is rendered THE SYSTEM SHALL require the UI to reach the server only
  through the host's MCP bridge, and SHALL NOT require the iframe to make a direct
  HTTP request to `tg.mctl.ai`.
- WHILE the prototype flag is enabled THE SYSTEM SHALL leave `OriginGuard`'s
  allowlist unchanged (`internal/web/origin.go:22`), because no new browser origin
  needs to reach the MCP endpoint.
- WHEN the App HTML is served THE SYSTEM SHALL carry a content security policy at
  least as strict as the existing "lite" tier
  (`default-src 'none'`, no remote script), matching the precedent in
  `internal/oauth/local_bridge_activate_page.go:131`.
- WHEN the App asset changes THE SYSTEM SHALL version it by content hash so a host
  can cache it safely and a reviewer can tell which build a screenshot came from.
- IF a registered tool is added or renamed for this spike THEN THE SYSTEM SHALL carry
  a matching entry in `docs/portal-allowlist.json`, because
  `internal/mcp/portal_allowlist_test.go` fails the build otherwise.

### Spike outputs

- WHEN the spike concludes THE SYSTEM SHALL have produced a host compatibility matrix
  covering the MCP Apps reference host, Claude.ai / the Claude connector, Claude
  Desktop or Code where relevant, and any ChatGPT MCP surface reached, each with
  observed rendering, tool invocation and confirmation behaviour.
- WHEN the spike concludes THE SYSTEM SHALL have produced a threat model covering
  iframe-to-tool invocation, untrusted Telegram content, identity and scope handling,
  and confirmation binding.
- WHEN the spike concludes THE SYSTEM SHALL have produced an implementation-path
  decision for the Go service, with evidence for or against `mark3labs/mcp-go v1.0.0`.
- WHEN the spike concludes THE SYSTEM SHALL have produced a submission-positioning
  note stating what capability is new relative to the plain tool connector, and this
  note SHALL NOT claim or imply that directory acceptance is assured.
- IF the product hypothesis is validated THEN THE SYSTEM SHALL have produced child
  implementation issues; IF it is not validated THEN THE SYSTEM SHALL have produced a
  written rejection with the evidence that settled it.

## Out of scope

- Shipping the App to production, enabling it by default, or submitting anything to
  the Claude connector directory or the ChatGPT app directory.
- Rebuilding a general Telegram client UI, or adding UI for tools outside the
  research/triage and single-draft-send flow.
- Giving the UI layer any Telegram API credential, MTProto session, or direct network
  path to Telegram.
- Duplicating Telegram business logic in a Node or TypeScript sidecar.
- Building a task, job or polling system for long-running App work; that belongs to
  the MCP Tasks spike (`mctlhq/.github#41`).
- Moving any authorization, rate limiting or confirmation decision into JavaScript.
- Changing the existing `send_message` contract for non-App callers, or making any
  new argument required on an existing tool.
- Multi-account selection inside the App; the spike uses the single identity the MCP
  request already carries.
- Media upload or `send_media` from the App; the action surface is text reply only.
- Any database migration or schema change.

## Open questions

- Which MCP Apps resource MIME type and metadata keys the current published extension
  actually mandates cannot be settled from this read-only clone, which has no network
  access and no module cache for `mark3labs/mcp-go`. Proceeding on the assumption
  that the App is delivered as an HTML resource under a `ui://` scheme referenced
  from tool `_meta`; task 1 verifies the exact contract against the live
  specification and the reference host, and the design is written so that only the
  adapter layer changes if the details differ.
- Whether `mark3labs/mcp-go v1.0.0` exposes resource registration plus per-tool
  `_meta` passthrough is unverified for the same reason. The library does carry an
  `mcp.Meta` type — `internal/mcpprobe/modern.go:14` already decodes `_meta` from an
  initialize response — which is evidence the concept exists in the library, not
  proof that the tool-declaration side is writable. Proceeding by making task 1 a
  hard go/no-go probe before any UI work starts.
- Whether Claude production surfaces render third-party MCP Apps at all today is
  explicitly flagged as unknown by the issue. Proceeding with the reference host as
  the primary target and treating Claude as a readiness checklist, exactly as the
  issue permits.
- Whether the App should be gated on a distinct OAuth scope rather than reusing the
  existing read scopes. Proceeding without a new scope, because the App invokes only
  tools the caller could already invoke; recorded as a decision for the threat model
  to revisit.
- Whether `prepare_send_message` should become the only supported send path once the
  spike ends, or remain an optional binding alongside today's draft-by-default
  behaviour. Proceeding with optional-and-additive so no existing client breaks, and
  deferring the stricter choice to a child issue.
- Whether the prototype flag should be an environment variable or a build tag.
  Proceeding with an environment variable, matching how `ALLOW_SEND`, `ToolFilter`
  and the demo reviewer id are already configured.
- What "realistic Telegram data fixtures" may contain is constrained by
  `.claude/CLAUDE.md`: fixtures must be synthetic and must reuse the existing
  `Alice`/`Bob`/`Carol`/`Dana` personas. Proceeding on that basis, with the live
  non-destructive account test kept out of the repository entirely.
