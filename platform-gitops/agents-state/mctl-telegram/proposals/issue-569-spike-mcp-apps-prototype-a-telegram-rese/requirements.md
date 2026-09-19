# Flag-gated MCP Apps prototype: Telegram research and triage App for Claude

## Context

`tg.mctl.ai` is today a pure tool surface: `internal/mcp/server.go` builds an
`mcpserver.NewMCPServer(...)` with `WithToolCapabilities(true)` and nothing
else — 30 tools, no resources, no prompts, no extensions. MCP Apps (SEP-1865,
extension id `io.modelcontextprotocol/ui`) standardises a second surface: a
server-declared HTML resource under the `ui://` scheme with mimeType
`text/html;profile=mcp-app`, linked to a tool through `_meta.ui`, rendered by
the host in a sandboxed iframe that talks back to the *host* (never to the
server) over postMessage using MCP JSON-RPC methods (`ui/initialize`,
`tools/call`, `resources/read`, `ui/notifications/tool-result`, ...). Issue
#569 asks whether this repository can expose such an App with the current Go
stack, and whether a research/triage App is a materially stronger product
shape than "Claude can call Telegram APIs".

Both questions are answerable inside this repository. `mark3labs/mcp-go
v1.0.0` — already the pinned dependency (`go.mod:14`) — carries every
primitive the extension needs: `server.WithExtensions(map[string]any)`
(`server/server.go:675`) for `capabilities.extensions`,
`MCPServer.AddResource` (`server/server.go:797`) with a free-form
`Resource.MIMEType`, `mcp.TextResourceContents.Meta map[string]any` whose own
doc comment says it "allows `_meta` to be used for MCP-UI features", and
`mcp.Tool.Meta *mcp.Meta` (`mcp/tools.go:657`) for the tool→UI link. What is
missing is not SDK capability but a decision, an implementation, and evidence.
This proposal builds the prototype behind a default-off flag, proves the
iframe cannot bypass a single existing server-side gate, and writes the
technical report from what the merged code actually does. Live host testing,
screenshots and connector-submission positioning are explicitly someone
else's work (`mctlhq/mctl-telegram#650`).

## User stories

- AS a Telegram power user I WANT a research and triage view rendered inside
  Claude SO THAT I can scan unread dialogs, search across channels and read
  message context without the model re-narrating every result as prose.
- AS the same user I WANT to draft a reply from a result card, see the exact
  recipient and the exact bytes that will be delivered, and be told up front
  whether the click will really send or only produce a preview SO THAT no
  consequential action ever happens as a surprise.
- AS the operator of `tg.mctl.ai` I WANT the App surface to be off by default
  and removable by one environment variable SO THAT the production connector's
  `tools/list` and `initialize` responses are byte-identical until I choose
  otherwise.
- AS a security reviewer I WANT proof that an iframe button click grants no
  authority — no scope, no identity, no send permission — SO THAT the App adds
  a rendering layer and not a second, weaker authorization path.
- AS a future connector submitter I WANT a written host-compatibility and
  readiness report grounded in the code SO THAT the live-host matrix in #650
  is a matter of filling rows, not of rediscovering the contract.

## Acceptance criteria (EARS)

Extension surface

- WHILE `MCP_APPS_ENABLED` is false (the default) THE SYSTEM SHALL advertise
  exactly the capabilities it advertises today — `tools` only, no `resources`,
  no `extensions` — and SHALL register exactly the tool set enumerated in
  `internal/mcp/server.go:newMCPServer` today, with no `_meta.ui` on any tool.
- WHEN `MCP_APPS_ENABLED` is true THE SYSTEM SHALL advertise
  `capabilities.extensions["io.modelcontextprotocol/ui"]` with
  `mimeTypes: ["text/html;profile=mcp-app"]` and SHALL advertise resource
  capability.
- WHEN a client issues `resources/list` with the flag on THE SYSTEM SHALL
  include a resource whose URI uses the `ui://` scheme and whose `mimeType` is
  exactly `text/html;profile=mcp-app`.
- WHEN a client issues `resources/read` for that URI THE SYSTEM SHALL return a
  single self-contained HTML document inline as `text`, with no external
  script, style, font, image or network origin referenced anywhere in it.
- WHEN the flag is on THE SYSTEM SHALL attach `_meta.ui` carrying
  `resourceUri` and `visibility` to the tools that back the App, using the
  nested object form, not the deprecated flat `ui/resourceUri` key.
- WHEN the App resource is read THE SYSTEM SHALL declare `_meta.ui.csp` with
  empty `connectDomains`, `resourceDomains`, `frameDomains` and
  `baseUriDomains`, so a conforming host applies a `default-src 'none'`
  baseline.

Research and triage flow

- WHEN the App starts THE SYSTEM SHALL allow it to populate itself using only
  the existing read tools `list_dialogs`, `get_unread_messages`,
  `get_messages`, `search_messages` and `prepare_get_media`, called through
  the host, with no new read tool introduced.
- WHEN a read tool is invoked from the App THE SYSTEM SHALL apply the same
  `requireScope` check it applies to a model-originated call
  (`telegram:dialogs:read` for `list_dialogs`, `telegram:messages:read` for
  the message tools) against the identity from `auth.From(ctx)`.
- WHILE rendering any Telegram-origin string THE APP SHALL insert it through a
  text node (`textContent`), never through `innerHTML`, `insertAdjacentHTML`,
  `document.write`, or any dynamic code-evaluation path.
- WHEN the App displays a message body THE SYSTEM SHALL have already passed
  that body through `sanitize.UserContent`, `sanitize.SensitiveTelegramContent`
  and `WrapUntrustedContent`, and the App SHALL strip only the outer
  `<telegram-content …></telegram-content>` envelope for display while keeping
  a visible untrusted-origin marker on the card.
- THE APP SHALL NOT send raw Telegram message text to the host via
  `ui/update-model-context` or `ui/message`.

Safe action surface

- WHEN the user drafts a reply in the App THE SYSTEM SHALL require a
  `prepare_send_message` call that returns a single-shot `confirmation_id`
  bound to `sha256(peer, NUL, text)` via the existing
  `HashSendPayload`, together with the verdict the send gate would reach right
  now and, when it would not really send, the `dry_reason`.
- WHEN `send_message` is called with a non-empty `confirmation_id` THE SYSTEM
  SHALL consume it against `HashSendPayload(peer, text)` before evaluating the
  send gate, and SHALL refuse the call if the confirmation is unknown,
  expired, already used, owned by a different identity, or bound to a
  different `(peer, text)` pair.
- WHEN `send_message` is called without a `confirmation_id` THE SYSTEM SHALL
  behave exactly as it does today, so existing model-driven clients are
  unaffected.
- WHILE any of the four send-gate conjuncts is unsatisfied — demo-reviewer
  identity, `ALLOW_SEND=false`, missing `telegram:messages:send` scope, or
  per-account `send_enabled=false` — THE SYSTEM SHALL return a successful
  `sent=false` dry-run preview and SHALL make no Telegram API call, regardless
  of what the App requested.
- IF the App supplies any parameter that would widen authority — a mode, a
  dry-run override, a scope, a subject, a user id — THEN THE SYSTEM SHALL
  ignore it, because no such parameter exists on the tool schemas.
- WHEN an App-originated send is evaluated THE SYSTEM SHALL debit the same
  per-(identity, peer) limiter (`evaluateDirectSendLimiter`) as a
  model-originated send.

Identity and isolation

- WHILE the App is rendered THE SYSTEM SHALL never place a Telegram session,
  MTProto credential, `TG_API_ID`/`TG_API_HASH`, OAuth token or bearer
  credential into the resource body or into any tool result the App reads.
- WHEN any App-originated call arrives THE SYSTEM SHALL derive identity solely
  from `auth.From(ctx)` populated by `auth.Middleware`, and SHALL NOT read any
  identity hint from tool arguments.
- IF an App-originated call carries a `confirmation_id` issued to another
  identity THEN THE SYSTEM SHALL fail with the existing
  `ErrConfirmationWrongUser` path and SHALL NOT perform the action.
- WHILE the flag is on THE SYSTEM SHALL keep `MCP_TOOL_FILTER=read-only`
  meaningful: with that filter set, no write tool — including
  `prepare_send_message` — is registered, and the App's draft affordance must
  degrade rather than call a tool that is not there.

Long-running research

- WHEN an App research flow would exceed a single synchronous tool call THE
  SYSTEM SHALL bound it with the caps that already exist (`limit` arguments,
  `BulkMediaFetchCap`, `MediaDownloadMaxBytes`) rather than introduce
  App-specific job polling.
- THE REPORT SHALL record which flows are near those bounds and what the
  mcp-go task primitives (`mcp/tasks.go`, `server/task_*.go`,
  `WithToolCallTasks`-style capability) would require, deferring to the MCP
  Tasks spike `mctlhq/.github#41`.

Evidence

- WHEN CI runs THE SYSTEM SHALL fail if the embedded App document references
  any external origin, uses `innerHTML`/`eval`/`Function(`/`document.write`,
  or drifts from its recorded content hash without that hash being updated.
- WHEN CI runs THE SYSTEM SHALL fail if `docs/portal-allowlist.json` does not
  carry an explicit decision for every registered tool, including any tool
  added by this proposal, per `internal/mcp/portal_allowlist_test.go`.
- WHEN the merged branch is built THE SYSTEM SHALL ship a technical report at
  `docs/reports/mcp-apps-spike.md` containing the host-compatibility matrix
  with the reference-host row filled from an automated probe, the threat
  model, the SDK/implementation-path decision with the concrete mcp-go symbols
  that justify it, the long-running-research assessment, and the
  submission-positioning note.

## Out of scope

- Live testing against claude.ai, Claude Desktop, Claude Code or ChatGPT;
  screenshots; video walkthrough; throwaway live Telegram account; connector
  or directory submission. All of that is `mctlhq/mctl-telegram#650` and
  depends on this prototype being merged and deployed.
- Any change to a sibling repository (`mctl-gitops`, `mctlhq/.github`,
  `mctl-web`). Deployment enablement of `MCP_APPS_ENABLED` is an operator
  action, not part of this PR.
- Turning the App on by default, or in production.
- A Node/TypeScript sidecar, a vendored fork of `mark3labs/mcp-go`, or an
  upstream SDK contribution.
- A general-purpose Telegram client UI: no dialog list management, no
  attachments composer, no contact management, no channel subscription.
- New read tools. The App composes only tools that already exist.
- A task/job system for long-running work. That is `mctlhq/.github#41`.
- Moving any safety decision into JavaScript.

## Open questions

- **Host-side `visibility` enforcement is not a server gate.** The spec has
  hosts reject `tools/call` from an App for tools lacking `"app"` in
  `_meta.ui.visibility`. That protects the *model* from App-only tools; it
  gives the server nothing. This proposal therefore treats `visibility` as a
  hint and keeps `requireScope` plus the send gate as the only authority.
  Proceeding on that interpretation.
- **Which tool carries `_meta.ui`.** The spec links a UI to a tool, and the
  natural anchor here is `get_unread_messages` (the triage entry point). An
  alternative is a thin dedicated `open_telegram_triage` tool. This proposal
  attaches `_meta.ui` to the existing read tools that the App opens from and
  adds no opener tool, to avoid a second tool whose only job is to exist.
  Revisit if a host turns out to require a distinguished opener.
- **`ui://` URI versioning.** The spec does not prescribe how a server
  versions an App. This proposal uses a stable URI
  (`ui://mctl-telegram/triage`) plus a build version inside `_meta` and a
  content-hash test, rather than baking a version into the URI, because a
  changing URI would break any host that cached the tool→resource link.
- **Extension negotiation on a stateless streamable-HTTP server.** mcp-go
  advertises `capabilities.extensions` from `initialize`; whether a host that
  does not negotiate the extension will still call `resources/read` for a
  `ui://` URI is host behaviour, not server behaviour. The prototype
  advertises correctly and the probe records what a client actually does.
- **`prepare_send_message` on the shared Cloudflare portal.** The portal
  allowlist is a per-server on/off switch that cannot see users. This proposal
  records the new tool as disabled there, since a prototype affordance should
  not appear on a shared surface. An operator can flip it later.
- **Whether the product hypothesis holds.** This proposal builds the artifact
  and writes an honest assessment; it does not and cannot claim directory
  acceptance, and the report is required to say so.
