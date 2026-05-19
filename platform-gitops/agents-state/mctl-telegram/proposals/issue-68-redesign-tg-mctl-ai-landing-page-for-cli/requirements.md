# Redesign tg.mctl.ai landing page for client-facing product audience

## Context

The current `internal/web/landing.html` is a 957-line single-page developer reference that
combines marketing copy, connector setup instructions, a full tool catalogue (9 rows), scopes
matrix, storage schema table, raw curl smoke-test commands, and a "Not zero-knowledge" warning
callout. It is well-suited for an operator or developer evaluating the project, but unsuitable
as the first screen a non-technical Claude.ai user sees when they follow a link to
`tg.mctl.ai`.

Issue #68 calls for separating concerns: the product-facing landing page becomes a brief,
persuasive page for clients with a clear CTA, while the reference documentation moves to a new
`/docs` route. A trust section replaces the blunt warning callout, and a FAQ addresses the most
common client questions. No changes to backend logic are required.

## User stories

- AS a prospective client I WANT to understand what "Telegram inside Claude" means in plain
  language SO THAT I can decide whether to add the connector in under 30 seconds.
- AS a prospective client I WANT to see concrete examples of what I can do SO THAT the
  value proposition is tangible and not abstract.
- AS a prospective client I WANT a single obvious button to add the connector SO THAT I do
  not have to hunt for setup instructions.
- AS a prospective client I WANT to understand how the connector is architecturally wired SO
  THAT I can evaluate whether the data flow is acceptable to me.
- AS a prospective client I WANT a plain-language explanation of the trust model SO THAT I
  can make an informed consent decision without reading security documentation first.
- AS a prospective client I WANT a FAQ that answers common concerns SO THAT I do not abandon
  the page over unanswered questions.
- AS a developer or operator I WANT all technical reference tables (tools, scopes, storage
  schema, smoke-test) to be available at `/docs` SO THAT they are not hidden but also not in
  the way of the client-facing page.
- AS an existing user I WANT the navigation to still reach /security and /privacy SO THAT
  the trust links remain accessible.

## Acceptance criteria (EARS)

- WHEN a visitor loads the root path `/` THE SYSTEM SHALL render a hero section with the
  headline "Your Telegram, inside Claude" and a sub-headline summarising the value
  proposition in one sentence.
- WHEN a visitor loads `/` THE SYSTEM SHALL display 2-3 use-case cards with concrete
  capability examples (e.g., "Summarise unread chats", "Draft and review messages",
  "Search across conversations").
- WHEN a visitor loads `/` THE SYSTEM SHALL render a primary call-to-action button labelled
  "Add to Claude" that links to `https://claude.ai/customize/connectors`.
- WHEN a visitor loads `/` THE SYSTEM SHALL render a how-it-works diagram showing the data
  flow: Claude.ai -- mctl-telegram -- Telegram MTProto.
- WHEN a visitor loads `/` THE SYSTEM SHALL render a trust section that acknowledges the
  server-side session model, names the specific mitigations (encryption, audit log, no
  message-body logging), and provides links to `/security` and `/privacy`.
- WHEN a visitor loads `/` THE SYSTEM SHALL render a FAQ section with at least five
  questions covering: data access, message sending safety, session revocation, open-source
  status, and the Local Bridge alternative.
- WHEN a visitor loads `/docs` THE SYSTEM SHALL render the full reference tables: tool
  catalogue (all 9 tools with mode, scope, and notes), scopes matrix, storage schema, and
  the smoke-test curl commands.
- WHEN a visitor loads `/docs` THE SYSTEM SHALL render the step-by-step connector setup
  instructions that were previously on the landing page, with the `{{.MCPURL}}` and
  `{{.WellKnownURL}}` template variables injected at serve time.
- WHILE the landing page renders THE SYSTEM SHALL preserve the existing theme toggle
  (dark/light) and accent picker controls in the top bar.
- WHILE the landing page renders THE SYSTEM SHALL preserve top-bar navigation links to
  `/docs`, `/security`, `/privacy`, and the GitHub repository.
- IF a browser sends a plain GET to the MCP endpoint (`Accept: text/html`, no JSON or SSE)
  THE SYSTEM SHALL continue to redirect to `/` unchanged (the `BrowserRedirect` handler in
  `internal/web/landing.go` is not modified).
- WHEN a visitor loads `/docs` THE SYSTEM SHALL inject the same four `landingData` template
  variables (`PublicBaseURL`, `MCPURL`, `WellKnownURL`, `AuthServer`) so the displayed
  endpoint URL is always correct for the deployment.
- WHILE CSS is loading or fails THE SYSTEM SHALL remain readable via the inline mctl design
  token fallback already present in the page `<head>`.

## Operator notes (added before accept)

The following requirements were identified in a pre-accept review of the live site
(`tg.mctl.ai`) and the repository. They extend the original issue scope.

### Track A — Docs consistency fix (prerequisite, ship first)

The live `/security` and `/privacy` pages, and sections of the README, still describe the
older `shared-hmac` / `api.mctl.ai` / GitHub-login auth model. The production deployment
uses `AUTH_MODE=local-jwt` and Telegram OIDC. This inconsistency is a trust problem for
prospective clients.

- WHEN a visitor loads `/security` THE SYSTEM SHALL NOT contain references to
  `shared-hmac`, `api.mctl.ai`, or GitHub OAuth as the auth mechanism (unless describing a
  deprecated mode).
- WHEN a visitor loads `/privacy` THE SYSTEM SHALL describe the current auth model
  (Telegram OIDC / local-jwt) consistently with `/security`.
- THE README auth sections SHALL agree with the production `AUTH_MODE=local-jwt` and
  Telegram OIDC configuration; stale references to `api.mctl.ai` + GitHub auth SHALL be
  removed or clearly marked as a legacy mode.
- Add tests that assert the auth-model terminology on `/security`, `/privacy`, and
  `/.well-known/oauth-protected-resource` is consistent (i.e., no stale model names).

### Secondary CTA

- WHEN a visitor loads `/` THE SYSTEM SHALL render a secondary CTA "Copy MCP URL" alongside
  the primary "Add to Claude" button, allowing power users to manually add the connector.

### Terminology consistency

- All pages, README sections, and new HTML SHALL use "Telegram sign-in" (not "Telegram Login
  Widget") unless the specific widget UI is still guaranteed by the current code path.
  The current `internal/oauth/server.go` uses Telegram OIDC; the landing copy SHALL match.

### Suggested implementation split

To reduce review risk the implementer SHOULD open separate PRs in this order:

| PR | Scope |
|----|-------|
| A  | Fix stale auth/trust copy on `/security`, `/privacy`, README; add consistency tests |
| B  | Add `/docs` route and move reference tables there |
| C  | Landing hero, use-case cards, how-it-works, trust section, FAQ, CTAs |
| D  | Funnel telemetry, browser error polish, optional CSP cleanup (deferrable) |

Each PR is independently mergeable. PRs B and C depend on A being merged first.

### Deploy smoke checks

Add integration/smoke tests (or at minimum `go test` assertions) for:
- `/` — returns HTTP 200, body contains "Your Telegram, inside Claude"
- `/security` — returns HTTP 200, body does not contain stale model names
- `/privacy` — returns HTTP 200
- `/.well-known/oauth-protected-resource` — returns HTTP 200, valid JSON

## Out of scope

- Changes to backend Go handler logic beyond adding a `/docs` route and serving the new
  `docs.html` template.
- Changes to OAuth/MCP endpoints.
- Internationalisation or multi-language support.
- Server-side analytics or A/B testing of page variants.
- Replacing the current mctl design system (ui.mctl.ai/mctl.css) with a different CSS
  framework.
- Adding new MCP tools or modifying existing tool behaviour.
- Changing the `BrowserRedirect` logic in `landing.go`.

## Open questions

1. **Exact CTA URL**: The issue specifies `https://claude.ai/customize/connectors` as the
   "Add to Claude" button target. Anthropic may change this URL; the implementer should
   verify the canonical deep-link before merge and consider whether a redirect at a stable
   path (e.g., `tg.mctl.ai/connect`) would be more durable.
2. **How-it-works diagram format**: The issue requests a "visual diagram". The existing
   page has no SVG assets; the most compatible approach is a pure-CSS/HTML flow strip.
   If the designer prefers an inline SVG, one must be authored. This proposal assumes a
   CSS-based diagram; the implementer can substitute SVG.
3. **FAQ content authority**: The issue does not enumerate the exact FAQ questions or
   answers. This proposal defines a minimum set of five; the product owner should review
   and extend before the page is considered production-ready.
4. **Top-bar `/docs` link**: The existing nav links are `#tools`, `#scopes`, `/security`,
   `/privacy`, `github`. Replacing `#tools` and `#scopes` with `/docs` changes a
   within-page anchor to a cross-page navigation. This is the most reasonable interpretation
   but should be confirmed with the designer.
5. **Smoke-test section in `/docs`**: The issue names the reference tables to move but does
   not explicitly mention the smoke-test curl block. This proposal moves it to `/docs` since
   it targets developers, not clients. If the product owner disagrees, it stays in `/docs`
   but is not linked from the new landing.
