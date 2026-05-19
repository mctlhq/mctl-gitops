# Design: issue-68-redesign-tg-mctl-ai-landing-page-for-cli

## Current state

### Serving layer (`internal/web/landing.go`)

`Landing()` in `internal/web/landing.go` (line 44) embeds `landing.html` via
`//go:embed landing.html` and parses it as a `html/template.Template`. It is registered
in `cmd/server/main.go` at line 141:

```go
mux.Get("/", web.Landing(cfg.PublicBaseURL, cfg.MCPPath, authServer))
```

The handler receives four deployment-specific values via `landingData`:

| Field           | Example value                              |
|-----------------|--------------------------------------------|
| `PublicBaseURL` | `https://tg.mctl.ai`                       |
| `MCPURL`        | `https://tg.mctl.ai/mcp`                   |
| `WellKnownURL`  | `https://tg.mctl.ai/.well-known/oauth-protected-resource` |
| `AuthServer`    | `https://tg.mctl.ai`                       |

`Security()` and `Privacy()` in `internal/web/security.go` use `//go:embed` on static byte
slices and serve them via the shared `staticPage()` helper. The same file embeds `privacy.html`.

There is currently no `/docs` route; the landing page contains all reference content inline.

### Current landing page content (`internal/web/landing.html`)

The 957-line page is organised into seven sections:

1. Hero — MCP connector headline and endpoint URL card
2. Trust callout — "Not zero-knowledge" warning (warn-coloured left border)
3. Connector setup — 5-step numbered list with `{{.MCPURL}}` and `{{.WellKnownURL}}`
4. Tools table — 9 rows: `list_dialogs`, `get_unread_messages`, `get_messages`,
   `send_message`, `pin_message`, `disconnect_telegram_account`, `delete_telegram_account`,
   `list_telegram_identities`, `set_telegram_access`
5. Scopes matrix — 3 rows mapping Telegram identity to OAuth scopes
6. Storage schema — 3 rows: `users`, `telegram_accounts.session_encrypted`, `audit_logs`
7. Smoke-test — raw curl commands using `{{.WellKnownURL}}` and `{{.MCPURL}}`
8. First-login — prose explanation of the in-browser MTProto login flow

Navigation in the top bar links to `#tools`, `#scopes`, `/security`, `/privacy`, GitHub.

The design system is sourced from `https://ui.mctl.ai/mctl.css` with an inline fallback
block for the mctl design tokens (lines 10-40), supporting dark/light theme and four accent
colours. Scripts are at the bottom of the file; CSP-compatible (no inline event handlers).

## Proposed solution

### Strategy: two-file split, one new handler

Split the existing single page into two distinct HTML templates:

- `internal/web/landing.html` — rewritten as the client-facing product page.
- `internal/web/docs.html` — new file containing the full reference documentation moved
  from the current landing page.

Add a `Docs()` handler to `internal/web/security.go` (or a new `internal/web/docs.go`)
alongside the existing `Security()` and `Privacy()` handlers, and register `/docs` in
`cmd/server/main.go`.

Because `/docs` surfaces the `{{.MCPURL}}` and `{{.WellKnownURL}}` values (connector setup
steps, smoke-test), it cannot be a static byte slice like `/security`. It must be a
`html/template` like the current landing — use the same `landingData` struct and
`landingTmpl`-style pattern.

### New `internal/web/landing.html` structure

The redesigned landing page replaces the current content with the following sections, in
order:

1. **Top bar** (unchanged structure, updated nav links)
   - Brand mark + "mctl-telegram" (unchanged)
   - Nav: "how it works" (anchor), "docs" (link to `/docs`), "security", "privacy",
     "github" external link, accent picker, theme toggle.
   - Remove `#tools` and `#scopes` anchors from nav (those sections move to `/docs`).

2. **Hero section**
   - Eyebrow: live status dot + "Operational · Remote MCP Server · v1" (unchanged).
   - `<h1>`: "Your Telegram,<br>inside Claude" — accent colour on "Claude".
   - Sub-headline (`.lead`): one sentence value proposition, e.g. "Give Claude read and
     write access to your Telegram chats — directly from claude.ai, with no extra apps."
   - Primary CTA button: `<a href="https://claude.ai/customize/connectors">Add to Claude</a>`,
     styled as a filled button using `var(--accent)` background.
   - Secondary link: "See the docs" pointing to `/docs`.

3. **Use-case cards** (`#use-cases`)
   - Three cards in a responsive CSS grid (three columns ≥ 720 px, one column on mobile).
   - Card 1 — "Summarise unread chats": Ask Claude what you missed while you were away.
   - Card 2 — "Draft and review messages": Let Claude write or check a reply before you send.
   - Card 3 — "Search across conversations": Find anything you said or received, instantly.
   - Each card: icon (ASCII/Unicode glyph or inline SVG), title, two-line description.
     Cards use the existing `.surface-card` background and `--border` border tokens.

4. **How it works** (`#how-it-works`)
   - Section heading "How it works".
   - A CSS-based three-node flow diagram: `[Claude.ai]` -- `[mctl-telegram]` -- `[Telegram]`
     with connecting arrows and one-line labels beneath each node.
   - Below the diagram: three numbered prose points explaining the data flow (auth, tool
     call, MTProto).

5. **Trust section** (`#trust`)
   - Heading "Our trust model", no warning colour — neutral card styling.
   - Lead sentence: acknowledges that the server holds a session on the user's behalf.
   - Three bullet points: (a) AES-256-GCM encrypted session at rest; (b) no message body
     or phone numbers logged (references `internal/audit/redact.go` in prose); (c) user
     controls: disconnect (soft) and delete (hard) at any time.
   - Links: "Read the full security model" -> `/security`, "Data retention policy" ->
     `/privacy`, "Audit your own log" -> `/docs#controls`.
   - Note on Local Bridge: one sentence on the planned Local Bridge mode as a stronger
     trust option, linking to GitHub readme.

6. **FAQ section** (`#faq`)
   - Heading "Common questions".
   - Accordion or simple definition-list of Q&A pairs. Minimum five items:
     - "Can Claude send messages on my behalf?" — explains `mode=draft` default and that
       real sends require `ALLOW_SEND=true` + `mode=send` + explicit opt-in.
     - "What data does mctl-telegram store?" — encrypted session blob only; no message
       text; audit log retains tool names and redacted peer references.
     - "How do I revoke access?" — disconnect tool, delete tool, or Telegram settings.
     - "Is this open source?" — yes, links to GitHub.
     - "What is the Local Bridge?" — explains planned M4 mode where session stays on
       the user's machine.

7. **Footer** (unchanged structure)
   - Add `/docs` link alongside `/security` and `/privacy`.

### New `internal/web/docs.html`

The docs page receives the same `landingData` template context. Content:

- Top bar and footer matching the new landing page.
- Connector setup section (the 5-step numbered list, with `{{.MCPURL}}`,
  `{{.WellKnownURL}}`).
- Tools table (all 9 tools with mode, scope, notes) — moved from current landing.
- Scopes matrix table — moved from current landing.
- Storage schema table — moved from current landing.
- Your controls section — moved from current landing (disconnect, delete, audit).
- Smoke-test section — moved from current landing (curl commands).
- First-login section — moved from current landing.

### New handler: `Docs()`

```go
// internal/web/docs.go  (or added to security.go)

//go:embed docs.html
var docsHTML string

var docsTmpl = template.Must(template.New("docs").Parse(docsHTML))

func Docs(publicBaseURL, mcpPath, authServer string) http.HandlerFunc {
    // identical parameter preparation as Landing()
    base := strings.TrimRight(publicBaseURL, "/")
    mcpPath = "/" + strings.TrimLeft(mcpPath, "/")
    if authServer == "" {
        authServer = base
    }
    data := landingData{
        PublicBaseURL: base,
        MCPURL:        base + mcpPath,
        WellKnownURL:  base + "/.well-known/oauth-protected-resource",
        AuthServer:    authServer,
    }
    return func(w http.ResponseWriter, _ *http.Request) {
        w.Header().Set("Content-Type", "text/html; charset=utf-8")
        w.Header().Set("Cache-Control", "no-store")
        _ = docsTmpl.Execute(w, data)
    }
}
```

### Route registration (`cmd/server/main.go`)

Add one line after the existing `/privacy` registration:

```go
mux.Get("/docs", web.Docs(cfg.PublicBaseURL, cfg.MCPPath, authServer))
```

No other changes to `main.go`.

### CSS additions (landing page only)

The new sections require a small number of new CSS rules added at the bottom of the
existing `<style>` blocks in `landing.html`:

- `.cta-btn` — filled button: `background: var(--accent)`, dark text, rounded corners
  (`var(--mctl-radius-md)`), hover darken via `filter: brightness(0.9)`.
- `.card-grid` — `display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px` with
  `@media (max-width: 640px)` fallback to one column.
- `.use-card` — card variant with top accent border, icon slot, title, body text.
- `.flow-diagram` — flex row with three node boxes and arrow connectors using `::before`
  pseudo-elements; collapses to vertical stack on mobile.
- `.faq-item` — definition-list styling: `dt` bold, `dd` indented with `var(--text-dim)`.

All new rules use only existing mctl design tokens; no new colour values are introduced.

## Alternatives

### Alternative A: Keep everything on one page, add anchor navigation

The reference tables remain on `/` but are collapsed behind `<details>` elements or a
JavaScript tab strip. The nav links `#tools` and `#scopes` continue to work.

Dropped because: it does not solve the core problem. A client who lands on the page still
sees a dense technical document with a "Not zero-knowledge" warning before any value
proposition. A collapsible is a cosmetic fix, not a structural one. The issue explicitly
requests moving reference content to a `/docs` page.

### Alternative B: Separate the landing entirely into a new Go package

Create `internal/web/product/` with its own handler, leaving `internal/web/landing.go`
untouched as the operator/developer landing.

Dropped because: it creates unnecessary package fragmentation for what is a content change.
The `internal/web` package is already the right home for all human-facing HTML. Adding a
second HTML template and handler to the existing package is simpler and follows the
existing pattern established by `security.go` (which hosts both `Security()` and
`Privacy()`).

### Alternative C: Render the page from Markdown or a template engine

Use `goldmark` (already referenced as an option in `security.go` line 16 comments) or a
similar library to render rich content from Markdown source.

Dropped because: the existing pattern in `internal/web/security.go` explicitly rejects this
approach ("Rendering markdown at request time would pull in goldmark for ~one page, which
isn't worth the binary-size cost"). Staying consistent with the project's own rationale is
correct; the HTML volume is manageable by hand.

## Platform impact

### Migrations

None. No schema changes, no new environment variables, no new configuration keys. The
`Docs()` handler reuses the existing `landingData` struct and the four config values already
passed to `Landing()`.

### Backward compatibility

- `/` continues to serve a valid HTML page; only its content changes.
- All existing nav anchors (`#tools`, `#scopes`, `#controls`, `#smoke`, `#setup`,
  `#first-login`, `#storage`) that may be bookmarked by developers will redirect to the
  new `/docs` page instead. Because those anchors are removed from `/` and added to `/docs`,
  bookmarks pointing to `tg.mctl.ai/#tools` will land on the root page without scrolling to
  the anchor. This is an acceptable regression for a developer-facing page that has no
  publicly advertised anchor links.
- The `BrowserRedirect` handler in `landing.go` (redirects browser GETs on `/mcp` to `/`)
  is unchanged.

### Resource impact

- Two additional HTML files embedded via `//go:embed` at compile time — negligible binary
  size increase (the current `landing.html` is ~30 KB unminified; `docs.html` will be
  similar in size once the reference tables are moved across).
- One additional `html/template.Template` parsed at startup — negligible.
- No new external dependencies.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| CTA URL `https://claude.ai/customize/connectors` becomes stale | Medium | Document it as a constant at the top of `landing.html` in a comment; add a note in `CONTRIBUTING.md` to verify the URL before each release. |
| How-it-works CSS diagram breaks on narrow screens | Low | Include `@media (max-width: 640px)` rule that collapses the three nodes to a vertical stack. |
| FAQ content is incomplete or inaccurate | Medium | Mark FAQ items with inline TODO comments; require product owner sign-off in PR review. |
| Existing developer bookmarks break for `#tools` / `#scopes` | Low | The anchors move from `/` to `/docs`; no customer-facing documentation links to them. Acceptable regression. |
