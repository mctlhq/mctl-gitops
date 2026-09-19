# Design: issue-569-spike-mcp-apps-prototype-a-telegram-rese

## Current state

**The MCP server is tools-only.** `internal/mcp/server.go:198`
(`newMCPServer`) is the single enumeration point of the surface:

```go
srv := mcpserver.NewMCPServer("mctl-telegram", v,
    mcpserver.WithToolCapabilities(true))
```

Thirty `{t, h := s.toolXxx(); s.addTool(srv, t, h)}` blocks follow. There is no
`AddResource`, no `AddResourceTemplate`, no `AddPrompt`, no
`WithResourceCapabilities`, no `WithExtensions`, no hooks. The transport is
`mcpserver.NewStreamableHTTPServer(..., WithHTTPContextFunc(httpContext))`
(`server.go:178`), where `httpContext` (`server.go:190`) folds
`edgectx.FromRequest(r)` into the tool context for audit correlation.

**Every tool is a `(mcplib.Tool, mcpserver.ToolHandlerFunc)` pair.** The
builder pattern is uniform, e.g. `toolListDialogs` (`internal/mcp/tools.go:183`):
`mcplib.NewTool(name, WithTitleAnnotation, WithReadOnlyHintAnnotation,
WithDestructiveHintAnnotation, WithOpenWorldHintAnnotation, outputSchema[T](),
WithDescription, WithString/WithNumber ...)`. `outputSchema[T]`
(`internal/mcp/output_schema.go:33`) is a local replacement for
`WithOutputSchema` that strips `"additionalProperties": false` so added
response fields are not breaking for a client holding a cached `tools/list`
(the #631/#637 regression, documented at `output_schema.go:11`). Results go
out through `jsonResult` (`tools.go:2180`), which emits both text and
`StructuredContent`.

**Authorization is entirely server-side and context-derived.** Each handler
starts with `id := auth.From(ctx)` (`internal/auth/identity.go:74`; the context
key is an unexported empty struct at `identity.go:65`), then
`requireScope(id, "...")` (`tools.go:1849`) or `requireAnyScope`
(`tools.go:1872`). The identity is injected by `auth.Middleware`
(`internal/auth/middleware.go:78`, injection at `:112`), which wraps the MCP
handler in `cmd/server/main.go:579-587`:

```go
mcpHandler := auth.Middleware(provider, cfg.AuthRequired, m, resourceMeta)(
    limiter.Middleware()(mcpSrv.HTTPHandler()))
guarded := web.OriginGuard(mcpHandler, cfg.AllowedOrigins)
mux.Mount(cfg.MCPPath, web.BrowserRedirect(guarded, "/"))
```

Because the middleware wraps the whole MCP handler, *every* JSON-RPC method on
`/mcp` — including a future `resources/read` — is authenticated identically.
Scope vocabulary in use: `telegram:dialogs:read`, `telegram:messages:read`,
`telegram:messages:send`, `telegram:messages:pin`, `account:manage`,
`admin:users`, `admin:users:read`.

**Writes are gated four ways, not by the client.** `evaluateWriteGate`
(`tools.go:1767`, wrapped by `evaluateSendGate` at `:1763`) requires: not the
pinned demo-reviewer identity, `ALLOW_SEND=true`, the required scope on the
identity, and per-account `send_enabled=true` in the DB — then
`evaluateDirectSendLimiter` (`tools.go:1834`) debits a per-(identity, peer)
bucket. A denied gate is not an error: `toolSendMessage`
(`tools.go:343`, gate at `:390-407`) returns a successful `sent=false` dry-run
preview audited as `send_message:draft`, and makes no Telegram call. There is
no `mode`, `dry_run` or `preview` argument on the tool; the only place
`args["mode"] = "send"` is set is server-side at `tools.go:416`, after the
gate passed, to tell a Local Bridge daemon to really send.

**Exact-payload binding already exists, partly unused.**
`internal/mcp/confirm.go` holds a single-shot in-memory `ConfirmStore` with a
10-minute TTL (`ConfirmationTTL`, `:15`), `Issue` (`:45`), `Consume` (`:87`),
`Claim`/`Unclaim`/`Finalize` (`:134`/`:172`/`:183`), the sentinels
`ErrConfirmationNotFound` / `ErrConfirmationMismatch` /
`ErrConfirmationWrongUser` / `ErrConfirmationInFlight` (`:66-81`), and three
canonical hashes: `HashSendPayload(peer, text)` (`:212`),
`HashMediaPayload` (`:222`), `HashPinPayload` (`:235`). `pin_message`
(`tools.go:632`) consumes a confirmation from `prepare_pin_message`
(`tools.go:568`); `get_media` (`media_tools.go:140`) claims one from
`prepare_get_media` (`media_tools.go:50`). **`HashSendPayload` has no caller in
non-test code** — the primitive for binding a send to its exact bytes is
written and tested but never wired.

**Untrusted Telegram content is already handled — for the model, not for a
DOM.** `internal/mcp/format.go:47` `wrapMessages` runs each body through
`sanitize.UserContent(m.Text, 4096)` then `sanitize.SensitiveTelegramContent`
(`internal/sanitize/sanitize.go:40`, `:85` — control/invisible-char stripping
and login-code/IP redaction), sanitizes `From`/`PeerTitle` via
`sanitize.Name`, and wraps the body in
`<telegram-content origin="telegram" peer=%q untrusted="true">…</telegram-content>`
(`format.go:33`), escaping any embedded closing tag so a sender cannot pivot
out of the block. `untrustedContentNotice` (`format.go:21`) is prepended to
read-tool results. Note what this is: an instruction-vs-data boundary for an
LLM. `internal/sanitize` performs **no HTML escaping** — it is not an XSS
sanitizer, and the wrapper it adds is itself tag-shaped text that a naive DOM
renderer would mangle.

**HTML is served today by embedding and inlining, never as static files.**
`internal/ui/chrome.go:24-34` `//go:embed`s four assets into `string` vars and
concatenates them into the template source (`chrome.go:71/76/77/131`). There
is no `embed.FS`, no `http.FileServer`, no `/assets/*` route anywhere in the
repo. The package has two tiers: full chrome (external Google Fonts plus
`https://ui.mctl.ai/0.5.0/mctl.css`, version-pinned and enforced by
`TestStylesheetIsVersionPinned`, `chrome_test.go:55`) and a lite strict-CSP
tier (`ui_head_lite`, `chrome.go:127`) with no external dependency at all,
locked in by `TestLiteChromeHasNoExternalDeps` (`chrome_test.go:76`), which
asserts the lite output contains no `mctl.css`, no `fonts.googleapis.com` and
no `<script` whatsoever. Strict pages set
`default-src 'none'; style-src 'unsafe-inline'; img-src https://ui.mctl.ai;
form-action 'self'; base-uri 'none'` (`internal/web/manage.go:244`,
`connect.go:356`, `internal/oauth/enable_access_page.go:355`).

**`OriginGuard` is on `/mcp` only and checks `Origin` alone**
(`internal/web/origin.go:22`): absent `Origin` is allowed on purpose, because
server-to-server MCP clients send none. An empty allowlist is a no-op;
`cmd/server/main.go` defaults it to the `PUBLIC_BASE_URL` origin.

**Diagnostics already exist for compatibility evidence.** `cmd/mcpprobe`
(`main.go`) plus `internal/mcpprobe` (`run.go:14` `Run`, `report.go:72`
`Report`, `modern.go`, `legacy.go`, `negative.go`, `readonly.go`,
`oauthprobe.go`) is a hand-run diagnostic whose stated purpose is to "produce
one row of compatibility evidence at a time".

**Build-time guard on the tool set.** `internal/mcp/portal_allowlist_test.go`
re-derives each registered tool's gate set from the Go AST and fails the build
unless `docs/portal-allowlist.json` carries an explicit decision and a
matching `upstream_gates` list for every tool.

**mcp-go v1.0.0 already has everything MCP Apps needs.** Checked in the module
cache at `github.com/mark3labs/mcp-go@v1.0.0`:

| Need (SEP-1865) | mcp-go v1.0.0 symbol |
| --- | --- |
| `capabilities.extensions["io.modelcontextprotocol/ui"]` | `server.WithExtensions(map[string]any)` — `server/server.go:675`, applied at `:1261`; `mcp.ServerCapabilities.Extensions` — `mcp/types.go:633` |
| Resource capability | `server.WithResourceCapabilities(subscribe, listChanged)` — `server/server.go:344` |
| `ui://` resource with a non-standard mimeType | `MCPServer.AddResource(mcp.Resource, ResourceHandlerFunc)` — `server/server.go:797`; `Resource.URI` / `Resource.MIMEType` are free strings — `mcp/types.go:883,897`; no scheme validation in `AddResources` |
| Resource `_meta` (`csp`, `prefersBorder`, …) | `mcp.Resource.Meta` — `mcp/types.go:881`; `mcp.TextResourceContents.Meta map[string]any` — `mcp/types.go:956`, doc: "Allows `_meta` to be used for MCP-UI features" |
| Tool `_meta.ui` | `mcp.Tool.Meta *mcp.Meta` — `mcp/tools.go:657`; `Meta.AdditionalFields` — `mcp/types.go:217`; `mcp.ToolOption` is `func(*Tool)` — `mcp/tools.go:887`, so a local option composes with the existing builders |
| Structured payloads for the UI | `CallToolResult.StructuredContent` — `mcp/tools.go:47`, already emitted by `jsonResult` |
| Long-running work | `mcp/tasks.go`, `server/task_hooks.go`, `toolCallTasks` capability |

There is no MCP-Apps *helper* in the SDK — no `NewUIResource`, no
`WithUIResourceMeta`. The metadata must be written by hand. That is a small
amount of literal JSON, not an SDK gap.

## Proposed solution

One flag-gated surface, added in a new package, composing tools that already
exist. Nothing is duplicated and nothing is moved into JavaScript.

### 1. Feature flag

`internal/config/config.go` gains `AppsEnabled bool` from
`MCP_APPS_ENABLED` (default `false`), documented in `.env.example` alongside
`AGENT_ENABLED`, which it mirrors. `cmd/server/main.go` threads it through a
new `mcpSrv.WithAppsEnabled(cfg.AppsEnabled)` in the existing option chain
(`main.go:463`). With the flag off, `newMCPServer` takes exactly the path it
takes today: the `initialize` response, `tools/list`, and every tool's `_meta`
are byte-identical to the current production surface. This is the rollback.

### 2. `internal/mcpui` — the App resource

A new package, deliberately separate because `internal/mcp/tools.go` is
already 123 KB, and because the asset-embedding precedent lives in a
UI package (`internal/ui`), not in the MCP package.

- `triage.html` — one self-contained document: markup, `<style>`, `<script>`,
  no external origin of any kind. Same discipline as the lite chrome tier.
- `app.go` — `//go:embed triage.html` into a `string` (matching
  `internal/ui/chrome.go:24-34`; an `embed.FS` would imply a file server, and
  there is no file server here), plus:
  - `const ResourceURI = "ui://mctl-telegram/triage"`
  - `const MIMEType = "text/html;profile=mcp-app"`
  - `const ExtensionID = "io.modelcontextprotocol/ui"`
  - `func Resource() mcplib.Resource` — name, title, description, MIMEType,
    and `Meta` carrying `ui: {csp: {connectDomains: [], resourceDomains: [],
    frameDomains: [], baseUriDomains: []}, prefersBorder: true}`.
  - `func Contents(uri string) []mcplib.ResourceContents` — a single
    `mcplib.TextResourceContents{URI, MIMEType, Text: triageHTML, Meta: …}`.
  - `func ExtensionCapability() map[string]any` — `{ExtensionID:
    {"mimeTypes": []string{MIMEType}}}`.
  - `func ToolMeta() map[string]any` — `{"ui": {"resourceUri": ResourceURI,
    "visibility": []string{"model", "app"}}}`, the nested form; the deprecated
    flat `ui/resourceUri` key is not emitted.

The URI is stable and unversioned; the build version travels in `_meta` and
drift is caught by a content-hash test (see Platform impact). A versioned URI
would break any host that cached the tool→resource link.

Delivering the document **inline through `resources/read`** is the answer to
the issue's hosting question. It needs no new HTTP route, no static origin, no
CDN, no cache policy and no CORS story; it inherits `auth.Middleware`, so the
App body is only readable by an authenticated identity; and it leaves
`OriginGuard` untouched, because the iframe never contacts `tg.mctl.ai` at all
— the host proxies `tools/call` and `resources/read` over its own MCP session.

### 3. `internal/mcp/apps.go` — wiring

- `func (s *Server) WithAppsEnabled(b bool) *Server` in `server.go`, plus an
  `AppsEnabled bool` field, following the existing `WithToolFilter` shape.
- In `newMCPServer`, when `s.AppsEnabled`:
  - append `mcpserver.WithResourceCapabilities(false, false)` and
    `mcpserver.WithExtensions(mcpui.ExtensionCapability())` to the
    `NewMCPServer` options;
  - `srv.AddResource(mcpui.Resource(), handler)` where the handler is
    `func(ctx, req) ([]mcplib.ResourceContents, error)` returning
    `mcpui.Contents(req.Params.URI)`. It reads `auth.From(ctx)` and refuses
    when the identity is nil, so an unauthenticated read cannot retrieve the
    App body even if a deployment runs with `AUTH_REQUIRED=false`.
- `func withUIResource() mcplib.ToolOption` — sets `t.Meta` from
  `mcpui.ToolMeta()`, preserving any existing `AdditionalFields`. Applied only
  when the flag is on, so the option is passed conditionally by a tiny helper
  rather than baked into the builders. The tools that receive it:
  `list_dialogs`, `get_unread_messages`, `get_messages`, `search_messages`,
  `prepare_get_media`, `prepare_send_message`, `send_message`.

`s.addTool` and `toolPassesFilter` (`server.go:163`) are untouched, so
`MCP_TOOL_FILTER=read-only` continues to remove every write tool from
`tools/list` — including the new prepare tool — regardless of the App flag.

### 4. The safe action surface

The issue's hardest requirement is that the UI must not be able to substitute
an iframe click for server authorization. The design answers it by adding
**one** tool and **one optional argument**, and by wiring the
already-written-but-unused `HashSendPayload`.

- `toolPrepareSendMessage()` in `apps.go` registers `prepare_send_message`,
  modelled on `toolPreparePinMessage` (`tools.go:568`). It takes `peer` and
  `text`, requires authentication, makes **no Telegram call**, and returns
  `{confirmation_id, peer_redacted, text, text_sha256, will_really_send,
  dry_reason, expires_at}`. `will_really_send`/`dry_reason` come from
  `evaluateSendGate(ctx, s.Store, id, s.AllowSend, s.DemoReviewerTGID)`, so
  the App can render "this will be delivered" versus "this is a preview only,
  because …" **before** the user clicks. `confirmation_id` comes from
  `s.Confirms.Issue(id.UserID, "send", HashSendPayload(peer, text))`.
  Registered only when `AppsEnabled`, so the default surface is unchanged.
- `toolSendMessage` gains an **optional** `confirmation_id` string. When
  non-empty, the handler calls
  `s.Confirms.Consume(confID, id.UserID, HashSendPayload(peer, text))` before
  `evaluateSendGate`, and maps the four sentinels to the same refusal messages
  `get_media` already uses (`media_tools.go:207-213`). When empty, the handler
  is byte-for-byte the behaviour it has today. Back-compat is deliberate: the
  confirmation is an *additional* binding, not a new gate, because the send
  gate was always the gate.

The resulting chain is exactly the one the issue draws, with the iframe at the
top and no shortcut around any box:

```
App UI  --postMessage-->  host  --tools/call on the host's own MCP session-->
  /mcp  ->  auth.Middleware (identity)  ->  limiter.Middleware
        ->  requireScope                 ->  Confirms.Consume(HashSendPayload)
        ->  evaluateSendGate (reviewer, ALLOW_SEND, scope, send_enabled)
        ->  evaluateDirectSendLimiter    ->  Telegram | dry-run preview
```

A click grants nothing. The App cannot set a scope (scopes come from the OAuth
token), cannot name an identity (there is no identity argument on any tool),
cannot request a real send (no `mode` argument exists), cannot read another
user's confirmation (`ErrConfirmationWrongUser`), and cannot silently swap the
body after the user approved it (`ErrConfirmationMismatch`).

### 5. Rendering untrusted Telegram content

The App consumes `structuredContent` from the read tools, which already
carries sanitized, redacted, envelope-wrapped text. On top of that:

- Every Telegram-derived string reaches the DOM via `textContent` on an
  element created with `document.createElement`. The document contains no
  `innerHTML`, no `insertAdjacentHTML`, no `document.write`, no `eval`, no
  `new Function`, no `setTimeout(string)`. A Go test greps the embedded asset
  for those substrings and fails the build, mirroring
  `TestLiteChromeHasNoExternalDeps`.
- The `<telegram-content …>` envelope is stripped for display by a strict
  prefix/suffix match against the exact literal shape `format.go:33` produces
  — not by a regex over arbitrary markup, and not by HTML parsing. If the
  shape does not match, the raw string is shown as-is (as text). The card
  keeps a visible "untrusted · Telegram" marker either way.
- The App never calls `ui/update-model-context` or `ui/message` with Telegram
  text. The only thing it hands the host is a tool call with arguments the
  user typed or selected.
- `_meta.ui.csp` declares no allowed domains, so a conforming host renders
  under `default-src 'none'`: no exfiltration channel exists even if a DOM
  injection were found.

### 6. Evidence, not assertions

- `internal/mcpprobe` gains an Apps conformance step (`apps.go`) plus report
  fields: does `initialize` advertise the extension id and mimeType; does
  `resources/list` contain a `ui://` URI with mimeType
  `text/html;profile=mcp-app`; does `resources/read` return non-empty inline
  text; do the expected tools carry nested `_meta.ui.resourceUri`. This fills
  the reference-host row of the compatibility matrix from an automated run
  rather than a human's recollection, and gives #650 a repeatable command for
  the live rows.
- `docs/reports/mcp-apps-spike.md` is the deliverable report: the matrix (with
  Claude/ChatGPT rows explicitly marked "not measured here — see #650" rather
  than guessed), the threat model, the SDK decision with the mcp-go symbol
  table above, the long-running-research assessment, and a
  submission-positioning note that states plainly that nothing here predicts
  directory acceptance. `claude-connector-submission.md:193` currently says
  this server has "**no** `ui/open-link` / interactive UI components /
  MCP-App widgets"; the report records that this becomes false once the flag
  is enabled in a deployment, and that the submission document is #650's to
  update.

## Alternatives

**A thin Node/TypeScript MCP Apps adapter in front of the Go service.**
Dropped. The official MCP Apps SDK would give ready-made UI resource helpers,
but it buys nothing the Go side lacks: `WithExtensions`, `AddResource`, a
free-form `MIMEType` and `Tool.Meta` are all present in the pinned v1.0.0. It
would cost a second deployable, a second auth hop (the adapter would need a
credential to reach `/mcp`, which is precisely the "duplicated credential
path" the acceptance criteria forbid), a second place where Telegram
semantics could drift, and a Node runtime in an image that is deliberately
Go-only (`Dockerfile`; `Dockerfile.agent-worker` exists as a separate image
precisely so the main one stays Go-only).

**Serve the App from a static origin (`tg.mctl.ai/apps/*` or a CDN).**
Dropped. It would be this repository's first static-asset route — there is no
`embed.FS` and no `http.FileServer` anywhere today — and would drag in
integrity hashing, cache policy, a CSP for a new HTML surface (the full-chrome
pages set none today), and an `OriginGuard`/CORS question for iframe fetches.
The spec's inline `resources/read` delivery avoids all of it and inherits
`auth.Middleware` for free. If a future App grows past a single file, revisit.

**Fork or patch `mark3labs/mcp-go` to add first-class MCP Apps helpers.**
Dropped for this spike. A fork is a maintenance liability, and the metadata in
question is a dozen literal JSON keys. An upstream contribution is worth
considering *after* the prototype proves the shape, and the report records
that as a possible follow-up — but it must not be on the critical path of a
spike whose point is to answer a question.

**Wire the App to a prepare/confirm flow built from scratch.** Dropped.
`ConfirmStore` already implements single-shot, TTL-bounded, identity-bound,
payload-hash-bound confirmations with four well-distinguished failure
sentinels and tests, and `HashSendPayload` is already written for exactly the
`(peer, text)` binding this needs. Building a parallel mechanism for the App
would be the "second weaker path" the issue explicitly warns against.

**Attach `_meta.ui` to a new dedicated `open_telegram_triage` tool.** Dropped
as the default (recorded as an open question). It adds a tool whose only
purpose is to exist, needs its own portal-allowlist decision, and would be
visible to the model in every session. Attaching the metadata to the read
tools the App genuinely composes is cheaper and reversible.

## Platform impact

**Migrations.** None. No schema change, no new table, no new column. The
confirmation store is in-memory and already exists.

**Backward compatibility.**
- Flag off (the default, and what is deployed): `initialize`, `tools/list`,
  `resources/list` (still absent) and every tool schema are unchanged.
- Flag on: the only tool-schema change to an existing tool is the *optional*
  `confirmation_id` on `send_message`. Optional input properties are additive.
  Output schemas are already open to additive fields by construction
  (`output_schema.go:33` strips `additionalProperties: false`), which is what
  keeps a host holding a cached `tools/list` from breaking — the exact failure
  mode of #631/#637.
- `docs/portal-allowlist.json` must gain an entry for `prepare_send_message`
  or `internal/mcp/portal_allowlist_test.go` fails the build. The entry is
  recorded as `enabled: false`: a prototype affordance does not belong on the
  shared Cloudflare portal surface. Because the tool is registered only when
  `AppsEnabled`, that test must construct its server with the flag on so the
  guard keeps covering the full set rather than silently skipping the new
  tool.

**Resource impact.** One embedded HTML document (tens of KB) in the binary and
resident in memory — the same cost profile as `internal/ui/assets`. One extra
`ConfirmStore` entry per drafted reply, bounded by the existing 10-minute TTL
and dropped single-shot. No new goroutine, no new connection, no new DB query
beyond the `IsSendEnabled` read that `prepare_send_message` performs and that
`get_my_send_status` already performs today.

**Risks and mitigations.**

| Risk | Mitigation |
| --- | --- |
| The extension contract shifts before `2026-07-28` ships broadly, and the literal keys go stale. | Every literal (`io.modelcontextprotocol/ui`, `ui://`, `text/html;profile=mcp-app`, `_meta.ui.resourceUri`) lives in exported constants in one package, `internal/mcpui`, and is asserted by the probe. A contract change is a one-file edit plus a probe run, not a hunt. |
| A host renders the App and a DOM-injection bug turns Telegram text into markup. | Text nodes only; a build-failing grep for `innerHTML`/`insertAdjacentHTML`/`document.write`/`eval`/`new Function`; `_meta.ui.csp` with no allowed domains so there is no exfiltration channel; the spec requires host-side iframe sandboxing on top. |
| The App is perceived as an authorization surface. | No server code path reads anything App-originated as authority. Identity comes only from `auth.From(ctx)`; scopes only from the token; the send gate is unchanged and still returns a dry-run preview whenever any conjunct fails. An adversarial test asserts a "send" issued through the App path with `send_enabled=false` produces `sent=false` and no Telegram call. |
| `_meta.ui.visibility` is mistaken for a gate. | Stated in the report's threat model and in the code comment on `ToolMeta()`: `visibility` is host-side model-hygiene, never server authorization. |
| The App surface accidentally ships enabled. | Default `false`; the flag is set nowhere in this PR; `cmd/server/main.go` logs the resolved value at startup; a test asserts the flag-off server advertises no `extensions` and no `resources` capability. |
| A confirmation is bound to a body the user never saw, because the App re-renders between prepare and send. | `HashSendPayload(peer, text)` is computed by the server from the arguments of both calls; any drift is `ErrConfirmationMismatch` and the row is dropped single-shot. The App displays `text_sha256` from the prepare result next to the draft. |
| `MCP_TOOL_FILTER=read-only` plus the App flag yields an App with a dead "send" button. | `prepare_send_message` carries `ReadOnlyHint=false`, so the existing filter removes it; the App feature-detects the tool in `tools/list` and hides the draft affordance when it is absent. Covered by a test. |
| The report over-claims. | The requirements forbid it, the matrix marks unmeasured rows as unmeasured, and `mctlhq/mctl-telegram#650` owns every live claim. |
