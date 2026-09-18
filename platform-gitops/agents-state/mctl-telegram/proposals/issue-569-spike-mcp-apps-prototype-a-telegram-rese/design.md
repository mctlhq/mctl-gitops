# Design: issue-569-spike-mcp-apps-prototype-a-telegram-rese

## Current state

### The MCP surface is tools-only

`internal/mcp/server.go:198` `newMCPServer` is the single enumeration point of the
protocol surface. It builds the server with exactly one capability:

```go
srv := mcpserver.NewMCPServer("mctl-telegram", v, mcpserver.WithToolCapabilities(true))
```

(`internal/mcp/server.go:203-207`), then registers 30 tools through `(*Server).addTool`
(`:172`), which filters on `Annotations.ReadOnlyHint` when `ToolFilter == "read-only"`
(`toolPassesFilter`, `:163`). There is no `WithResourceCapabilities`, no `AddResource`,
no `AddResourceTemplate`, no `AddPrompt`, and no `_meta` emission anywhere in
`internal/mcp`. A repo-wide grep confirms it: the only `mcp.Meta` use is read-side, in
`internal/mcpprobe/modern.go:14`, which decodes `_meta` from a `server/discover`
response and calls `parsed.Meta.ServerInfo()` (`:57`). So the concept exists in the
vendored library; this server simply never writes one.

Indirect evidence that `mark3labs/mcp-go v1.0.0` can carry the resource half:
`go.mod` pulls `github.com/yosida95/uritemplate/v3 v3.0.2` as an indirect dependency,
which mcp-go uses for resource templates, and `github.com/google/jsonschema-go` for
schema reflection. That is suggestive, not conclusive — this clone is offline with no
module cache — so the spike treats it as a hypothesis to falsify first, not a fact.

### The read tools already emit the exact data an App would render

Every read tool returns both a JSON text block and machine-readable structured
content through one helper, `jsonResult` (`internal/mcp/tools.go:2180`):

```go
res := mcplib.NewToolResultText(string(b))
res.StructuredContent = v
```

Schemas are declared by `outputSchema[T]()` (`internal/mcp/output_schema.go:33`), which
reflects the Go result struct and then strips every `"additionalProperties": false`
via `openAdditiveFields` (`:85`) so additive fields never break a client holding a
cached `tools/list` — the lesson of the Cloudflare portal incident documented at
`internal/mcp/output_schema.go:10-31`. Result structs live at `tools.go:1925`
(`listDialogsResult`), `:1932` (`messagesResult`), `:2355` (`searchMessagesResult`),
and `media_tools.go:20`/`:32`. `search_messages` is the one read tool that bypasses
`jsonResult`, hand-building its result so it can prefix `untrustedContentNotice`
(`tools.go:2596-2602`) — it still sets `StructuredContent`.

The consequence for this spike is large: **an App needs no new Telegram data path.**
It can render `structuredContent` that the server already produces and already
validates against a published schema.

### Untrusted Telegram content is already marked, but marked for an LLM, not for a DOM

`internal/mcp/format.go:47` `wrapMessages` sanitizes each message through
`sanitize.UserContent` (control and invisible characters, excessive newlines, 4096-rune
cap), `sanitize.SensitiveTelegramContent` (login codes, login IPs —
`internal/sanitize/sanitize.go:85`) and `sanitize.Name`, then calls
`WrapUntrustedContent` (`format.go:32`), which produces:

```
<telegram-content origin="telegram" peer="..." untrusted="true">BODY</telegram-content>
```

escaping any forged closing tag in the body. Two facts matter for a UI. First, that
envelope is *inside* `Message.Text` in the structured content, so an App that renders
the field naively shows literal angle-bracket markup to the user. Second,
`sanitize.UserContent` does **not** HTML-escape — it was designed for an LLM
transcript, not a document. Rendering that string through `innerHTML` would be a
stored-XSS path fed directly by arbitrary Telegram senders.

### Writes are gated server-side, but `send_message` has no payload binding

Two different mechanisms exist, and only one covers sends.

The gate: `evaluateWriteGate` (`tools.go:1767`) and its pre-account half
`evaluateWriteGateBeforeAccount` (`:1794`) decide, in order — demo reviewer identity
(forced preview, `:1806`), `ALLOW_SEND` (`:1809`), the required scope (`:1812`), then
per-account `send_enabled` via `evaluateSendGateAccountFlag` (`:1827`). A closed gate
returns a *successful* dry-run preview with `sent=false` and a `dry_reason`
(`tools.go:397-407`), never an error. Rate limiting is a separate tap:
`evaluateDirectSendLimiterN` (`:1842`) against `audit.PeerSendCap` (20/hour/peer).

The binding: `ConfirmStore` (`internal/mcp/confirm.go`) issues a single-shot,
10-minute, identity-bound confirmation whose `PayloadHash` pins the exact arguments —
`Issue` (`:45`), `Consume` (`:87`, deletes before validating, collapses expiry and
unknown into one error), `Claim`/`Unclaim`/`Finalize` for long downloads (`:134`,
`:172`, `:183`). `prepare_pin_message`/`pin_message` use it (`tools.go:611`, `:686`)
and `prepare_get_media`/`get_media` use it (`media_tools.go:121`, `:195`).

`send_message` uses neither half of the binding. `toolSendMessage` (`tools.go:343`)
declares only `peer` and `text` and relies on draft-by-default plus whatever
confirmation UI the host chooses to show. Tellingly, `HashSendPayload`
(`confirm.go:212`) exists with a doc comment describing exactly this flow and has
**no caller in the repository.** For a chat-driven connector that is defensible: the
host renders the tool call and the user reads the arguments. For an App it is not,
because the thing the user reads is a textarea the App controls, and the issue is
explicit that an iframe click must not substitute for server-side authorization.

### Transport, guards and identity

`HTTPHandler` (`server.go:178`) returns `mcpserver.NewStreamableHTTPServer` with
`WithHTTPContextFunc(httpContext)`; there is no SSE server in the repo. The mount
chain in `cmd/server/main.go:577-587` is, outermost first: `web.BrowserRedirect` →
`web.OriginGuard(..., cfg.AllowedOrigins)` → `auth.Middleware(provider, ...)` →
`limiter.Middleware()` → the MCP handler. `OriginGuard` (`internal/web/origin.go:22`)
allows a request with no `Origin` header (server-to-server MCP clients send none) and
403s a browser `Origin` outside the allowlist. Identity reaches tools only through
`auth.From(ctx)` (`internal/auth/identity.go:71`), checked by `requireScope`
(`tools.go:1849`) and `requireAnyScope` (`:1872`) against the scope set
`telegram:dialogs:read`, `telegram:messages:read`, `telegram:messages:send`,
`telegram:messages:pin`, `admin:users`, `admin:users:read`.

Local Bridge mode diverts reads and writes to the user's daemon via `bridgeCall`
(`tools.go:113`), which decodes the daemon's JSON generically into a map so
`StructuredContent` stays present (`:164-168`). `fetch_media` is explicitly refused on
that path (`:282`), which is why an App must use `prepare_get_media`/`get_media` there.

### HTML, CSP and asset conventions

Human pages are `go:embed`-ed templates rendered through `chromePage`
(`internal/web/security.go:15`) with `Cache-Control: no-store`. The shared chrome
package `internal/ui/chrome.go` documents two tiers (`:7-16`): a "full" tier that
loads `https://ui.mctl.ai/0.5.0/mctl.css` and Google Fonts, and a "lite" tier for
strict-CSP pages with everything inlined. The strict precedent is
`internal/oauth/local_bridge_activate_page.go:131`:

```
default-src 'none'; style-src 'unsafe-inline'; img-src https://ui.mctl.ai; form-action 'self' https:; base-uri 'none'
```

with nonce-based variants at `internal/web/connect.go:358`, `manage.go:246` and
`internal/oauth/enable_access_page.go:361`. There is no content-hash asset pipeline;
local CSS/JS are inlined, and the two remote pins are hand-versioned strings
(`chrome.go:50`, `:75`).

### The submission currently declares the opposite of this spike

`claude-connector-submission.md:191-194` states that this is a remote MCP server with
no `ui/open-link`, no interactive UI components and no MCP-App widgets, and that
MCP-App carousel screenshots are not applicable. That declaration is a deliverable of
the spike, not a bystander: validating the hypothesis means amending it.

### Guards that will fail the build if the spike is careless

- `internal/mcp/portal_allowlist_test.go` re-derives each tool's gate set from the Go
  source and holds `docs/portal-allowlist.json` to the exact tool list in
  `newMCPServer`. A new registered tool without an allowlist entry fails CI.
- `internal/mcp/annotations_test.go:14` `TestToolAnnotations` is a table over every
  `toolXxx()` builder; a new builder must be added to it.
- `internal/mcp/output_schema_open_test.go` `TestOutputSchemasStayOpenToAdditiveFields`
  and `TestToolOutputSchemas` fail any tool that publishes no output schema or a
  closed one.
- CI (`.github/workflows/build.yml`) runs `go vet ./...`, `go build ./...` and
  `go test -race ./...`; cross-compiles darwin/arm64 and windows/amd64 for `cmd/local`.
  There is no Makefile.

## Proposed solution

A single flag-gated vertical slice inside the existing Go service, plus a written
evidence pack. Nothing new is deployed by default and no Telegram logic leaves Go.

### Shape

```
MCP host (reference host, then Claude)
  │  resources/read  ui://mctl-telegram/triage
  ▼
internal/mcp/appui  ──►  self-contained HTML/CSS/JS, go:embed, content-hashed
  │
  │  host renders in its sandboxed iframe (origin null)
  │  iframe ──postMessage──► host ──tools/call──► tg.mctl.ai
  ▼
existing tool handlers, unchanged
  auth.From(ctx) → requireScope → evaluateWriteGate → ConfirmStore → limiter → audit
  ▼
Telegram (hosted pool) or Local Bridge daemon
```

The load-bearing property is that the iframe never talks to `tg.mctl.ai`. It asks the
host to call a tool; the host calls the same authenticated endpoint a chat turn would.
`OriginGuard` therefore needs no allowlist change, and no browser origin gains access
to `/mcp`. This is also why the App HTML must be fully self-contained: a sandboxed,
`null`-origin document cannot be relied on to fetch anything, and fetching would
reintroduce the origin problem we just avoided.

### Change 1 — go/no-go probe on the SDK (before any UI work)

A throwaway `cmd/` harness or a `//go:build spike` test that attempts, against
`mark3labs/mcp-go v1.0.0`: declaring a resource capability, registering a static
resource and a resource template, serving a non-JSON MIME type, and attaching `_meta`
to a tool declaration and reading it back over streamable HTTP. The outcome is
recorded in `docs/plans/mcp-apps-spike.md` as one of: the SDK suffices; it needs a
narrowly scoped upstream contribution (with the patch sketched); or it cannot express
the contract and the direction is rejected. No UI work starts until this is written
down. If the answer is "needs upstream", the fallback for the spike only is to attach
the resource surface with a small in-repo `http.Handler` shim in front of the MCP
handler that answers `resources/list` and `resources/read` and delegates everything
else — a spike-local scaffold, explicitly not a shipping design.

### Change 2 — `internal/mcp/appui`, a new package holding only presentation

`appui` owns the HTML document, the resource descriptor, and nothing else. It imports
no Telegram package, holds no credential, and has no access to `*db.Store` or
`*telegram.ClientPool`. It exposes roughly:

- `//go:embed assets/triage.html` plus a `Version()` that is the SHA-256 prefix of the
  embedded bytes, computed in an `init`. That is the asset versioning story: the
  content hash is the version, it appears in the resource URI
  (`ui://mctl-telegram/triage?v=<hash>`) and in a corner of the UI so a screenshot
  identifies its build. This is a strict improvement on the hand-pinned strings at
  `internal/ui/chrome.go:50,75`, and deliberately avoids inventing a build pipeline.
- `Resource() (mcplib.Resource, handler)` returning the document with the MIME type
  the extension mandates (confirmed in change 1) and the strict-CSP meta baked in,
  modelled on the "lite" tier — `default-src 'none'; style-src 'unsafe-inline'`, no
  remote script, no remote font, no remote image. Unlike the lite tier it must not
  allow `img-src https://ui.mctl.ai`, because the iframe has no reliable network.

Registration happens in `newMCPServer` behind the flag:

```go
if s.AppUI {
    srv = mcpserver.NewMCPServer(..., mcpserver.WithToolCapabilities(true),
        mcpserver.WithResourceCapabilities(false, false))
    srv.AddResource(appui.Resource())
}
```

wired by a `WithAppUI(bool)` builder alongside the existing `WithToolFilter` /
`WithDemoReviewer` chain (`server.go:86-159`), fed from a new `TG_MCP_APPS` config
field defaulting to false. With the flag off the capability set, the tool list and
every schema are byte-identical to today, which is the compatibility contract in
requirements.

### Change 3 — the research surface reuses existing tools verbatim

The App composes `list_dialogs`, `get_unread_messages`, `get_messages`,
`search_messages` and `prepare_get_media`/`get_media`. No tool gains an argument, no
tool changes shape, and the App consumes `structuredContent` — so the open-schema
discipline of `output_schema.go` keeps working in its favour rather than against it.

Two presentation rules are non-negotiable and are the App's whole reason to exist as a
security artifact rather than a demo:

1. **Unwrap, then insert as text.** The renderer strips the
   `<telegram-content …>` envelope that `WrapUntrustedContent` adds, and writes the
   body via `textContent` only. `innerHTML` is banned outright; the CSP with no
   `script-src` and no inline handlers is the backstop. Every message card carries a
   persistent "from Telegram — untrusted" marker, so the UI keeps the boundary
   `untrustedContentNotice` (`format.go:21`) states in prose.
2. **No content-derived actions.** Nothing in a message body may populate a tool
   argument, prefill a draft, or be forwarded to the host as a prompt without an
   explicit user gesture. This is the iframe-side mirror of the rule the notice
   already asks the model to follow.

Pagination uses the tools' own `limit` and `next_before_id` (`messagesResult`,
`tools.go:1932`) with a visible "showing N of more" state. Nothing polls. If a
research flow genuinely outgrows a synchronous call, the spike records the shape and
defers to `mctlhq/.github#41` rather than inventing job polling — the existing
`internal/agent/queue` machinery is the Communication Agent's REST worker queue and is
deliberately not reused here.

In Local Bridge mode the App works unchanged over `bridgeCall`, except that media goes
through `prepare_get_media`/`get_media` because `fetch_media` is refused on that path
(`tools.go:282`). Under `ToolFilter = "read-only"` the research surface renders and
the action surface renders as unavailable, driven by what `tools/list` actually
contains rather than by a hardcoded assumption.

### Change 4 — `prepare_send_message`, closing the binding gap

A new tool `prepare_send_message` mirrors `prepare_pin_message` (`tools.go:568`):
require `telegram:messages:send`, take the per-peer limiter tap, then
`s.Confirms.Issue(id.UserID, "send", HashSendPayload(peer, text))` and return
`{confirmation_id, peer_redacted, text_preview, expires_at, would_send, dry_reason}` —
where `would_send` is `evaluateSendGate`'s verdict evaluated at prepare time, so the
App can show "this will actually be delivered" versus "this will be a preview" *before*
the user commits, which is precisely the "see exactly what will happen" clause of the
issue's acceptance criteria.

`send_message` gains one **optional** `confirmation_id` argument. When absent,
behaviour is byte-identical to today (no existing client breaks, no argument becomes
required). When present, the handler calls
`s.Confirms.Consume(confID, id.UserID, HashSendPayload(peer, text))` before sending and
maps the three sentinels to the same distinct messages `pin_message` uses
(`tools.go:689-693`). The App always sends the id. The gate ordering follows
`pin_message`: evaluate the write gate first, consume second, so a dry-run does not
burn a confirmation.

This is additive by construction and it makes the App's central claim testable: change
the text after prepare and the send must fail with `ErrConfirmationMismatch`; present
another user's id and it must fail with `ErrConfirmationWrongUser`.

The new tool requires a `docs/portal-allowlist.json` entry with `upstream_gates`
`["send-gate", "telegram:messages:send"]` and a row in `TestToolAnnotations`
(`readOnly=false`, `destructive=false` — prepare mints a handle, it delivers nothing —
`openWorld=false`), or CI fails.

### Change 5 — the evidence pack

Following the repo's existing convention (`docs/plans/<topic>.md` as the canonical
dated plan, `docs/reports/<topic>-<phase>.md` for results, per
`docs/plans/communication-agent.md`):

- `docs/plans/mcp-apps-spike.md` — the plan, the SDK decision, and a dated status line.
- `docs/reports/mcp-apps-host-matrix.md` — the compatibility matrix with observed
  behaviour per host and the date each row was tested, since host support is moving.
- `docs/reports/mcp-apps-threat-model.md` — iframe-to-tool invocation, untrusted
  content rendering, identity and scope handling, confirmation binding, and the
  residual risks the spike did not close.
- A submission-positioning note stating what is new versus the plain tool connector,
  with an explicit sentence that directory acceptance is not implied, plus the edit
  that `claude-connector-submission.md:191-194` would need. The edit is *drafted*, not
  applied, because the current declaration is accurate for the current shipping build.

Screenshots and video go to the issue, not the repository — the repo has no media
convention beyond `internal/web/walkthrough.mp4`, and a spike should not grow one.

Fixtures for the polished flow are synthetic and reuse `Alice`/`Bob`/`Carol`/`Dana` as
`.claude/CLAUDE.md` requires; the live non-destructive account run is performed against
a throwaway account and recorded only as prose in the report.

## Alternatives

**A Node/TypeScript MCP Apps sidecar using the official SDK, proxying to the Go
service.** Attractive because the reference SDK would certainly support the extension
on day one. Dropped: it creates a second process that must authenticate as the user to
the Go server, which means either forwarding the caller's token (a new confidential
hop that can strip or mint scopes) or minting a service credential (which breaks the
invariant that identity comes from `auth.From(ctx)` on the original request). The
issue names avoiding a sidecar as a non-goal, and `internal/workertoken` exists
precisely because credential hops here are expensive to get right. The UI-only benefit
does not justify a new trust boundary in front of `evaluateWriteGate`.

**Serving the App HTML from `tg.mctl.ai` over HTTP, or from a dedicated static origin
under `ui.mctl.ai`.** This is how the human pages work today (`internal/web`,
`internal/ui/chrome.go`) so it is the path of least surprise. Dropped for the spike:
an HTTP-fetched document in a host iframe is a real browser origin, which drags in
`OriginGuard` allowlist changes (`internal/web/origin.go:22`), a CSP that must permit
a remote origin, a cache policy, and subresource-integrity versioning — four new
decisions, all of which the extension's own resource-delivery model makes unnecessary.
Delivering the document through `resources/read` keeps the whole surface inside the
authenticated MCP channel. If the extension turns out to require an HTTP-hosted asset,
change 1 will surface it and this alternative becomes the design instead.

**Forking or patching `mark3labs/mcp-go` up front.** Dropped as a starting position:
the indirect `uritemplate/v3` dependency and the existing `mcp.Meta` type in
`internal/mcpprobe/modern.go:14` both suggest the library already carries what is
needed, and a fork is a permanent maintenance cost taken on speculation. Change 1
makes it a decision with evidence; a narrowly scoped upstream contribution remains the
preferred outcome if the probe shows a gap.

**Making `confirmation_id` required on `send_message`.** Cleaner as a security
property, and it would put every send behind exact-payload binding. Dropped for this
spike because it is a breaking change to a tool that ships in a connector already
under directory review, and because `docs/portal-allowlist.json` and the Cloudflare
portal hold cached catalogues whose staleness has already caused one production
incident (`internal/mcp/output_schema.go:23-30`). Recorded as a child issue.

## Platform impact

**Migrations.** None. `ConfirmStore` is in-memory by design (`confirm.go:20`), the App
holds no state, and no table changes.

**Backward compatibility.** With `TG_MCP_APPS=false` — the default, and what
production runs — the initialize response, the capability set, the tool list and every
input and output schema are unchanged. With the flag on, the only protocol delta is an
added resources capability and one resource; no existing tool changes, and
`send_message`'s new argument is optional, so a client holding a cached `tools/list`
keeps working. The additive-open schema discipline in `output_schema.go:33` already
protects the `prepare_send_message` result from the frozen-catalogue failure mode of
#637.

**Resource impact.** Negligible. One embedded HTML document of a few tens of
kilobytes, served from memory. The App issues the same tool calls a chat turn would;
if anything it issues fewer, because a UI filter re-invokes one tool instead of asking
a model to re-read a transcript. Per-peer send limiting is unchanged.

**Risks and mitigations.**

- *A host renders the App but does not enforce the confirmation step, and a UI click
  reaches `send_message` directly.* Mitigated by the gate ordering, which is
  server-side and host-independent: `evaluateSendGate` still applies, and with the App
  always supplying a `confirmation_id` bound to the exact `(peer, text)`, a swapped
  payload fails closed. Stated as an explicit test, not an assumption.
- *Stored XSS from a Telegram message body.* Mitigated by text-only insertion, the
  `innerHTML` ban, a CSP with no `script-src`, and an adversarial fixture set modelled
  on `internal/agent/policy/adversarial_output_test.go`. The residual risk — a host
  that ignores the CSP — is recorded in the threat model rather than waved away.
- *Adding a resources capability breaks a client that assumed tools-only.* Mitigated by
  the default-off flag and by probing the deployed surface with the existing
  `cmd/mcpprobe` before and after enabling it anywhere.
- *Claude does not support third-party MCP Apps during the spike window.* Accepted by
  design: the reference host is the primary target and the Claude row becomes a dated
  readiness checklist, which the issue explicitly permits.
- *The spike quietly becomes a product.* Mitigated by keeping the flag off, keeping the
  `claude-connector-submission.md` amendment drafted-not-applied, and requiring the
  positioning note to state that acceptance is not implied.
- *Scope creep into a Telegram client.* Mitigated by the single research flow plus a
  single text-reply action, with media upload and multi-account explicitly out of
  scope.
