# Tasks: issue-68-redesign-tg-mctl-ai-landing-page-for-cli

- [ ] 1. Create `internal/web/docs.html` — new reference documentation page
  (depends on nothing)
  DoD: File exists at `internal/web/docs.html`. Contains, in order: top bar (matching
  the updated landing nav), connector setup section (5-step list with `{{.MCPURL}}` and
  `{{.WellKnownURL}}`), tools table (all 9 tools), scopes matrix table, storage schema
  table, your-controls list, smoke-test pre block, first-login prose, and footer. All
  content is moved verbatim from the current `internal/web/landing.html` with only the
  nav links updated. `go build ./...` passes.

- [ ] 2. Add `Docs()` handler in `internal/web/` and register `/docs` route
  (depends on 1)
  DoD: Either `internal/web/docs.go` is created or `Docs()` is appended to
  `internal/web/security.go`. The function mirrors `Landing()` in signature:
  `func Docs(publicBaseURL, mcpPath, authServer string) http.HandlerFunc`. It embeds
  `docs.html` via `//go:embed docs.html`, parses it as a `html/template.Template`, uses
  the existing `landingData` struct, and sets `Cache-Control: no-store`. In
  `cmd/server/main.go`, the line `mux.Get("/docs", web.Docs(cfg.PublicBaseURL, cfg.MCPPath, authServer))`
  is added after the `/privacy` registration (line 143). `go vet ./...` passes.

- [ ] 3. Rewrite `internal/web/landing.html` — client-facing product page
  (depends on 2, so that docs.html already holds the reference content being removed)
  DoD: `internal/web/landing.html` is rewritten to contain the following sections and
  nothing else: top bar (with nav links updated to include `/docs`), hero section with
  `<h1>Your Telegram, inside Claude</h1>`, `.lead` sub-headline, `.cta-btn` "Add to Claude"
  link to `https://claude.ai/customize/connectors`, secondary "See the docs" link to `/docs`,
  use-case cards section (`#use-cases`, three cards), how-it-works diagram (`#how-it-works`),
  trust section (`#trust`, neutral styling — no warn-coloured callout), FAQ section (`#faq`,
  minimum five Q&A items), and footer. All four template variables (`{{.MCPURL}}`,
  `{{.WellKnownURL}}`, `{{.AuthServer}}`, `{{.PublicBaseURL}}`) that the `landingData` struct
  provides must still be used or present (even if only in a comment) so the template parses
  without error. The MCP endpoint URL is kept in the trust section or a secondary callout
  for users who want to add the connector manually. The existing inline mctl design-token
  fallback block (`:root { --mctl-accent-cyan-primary: ... }`) and pre-paint theme script
  are preserved verbatim. The theme toggle and accent picker remain in the top bar.
  `go build ./...` passes; `go test ./internal/web/...` passes.

- [ ] 4. Add CSS for new landing page components
  (depends on 3, part of the same file edit)
  DoD: The `<style>` block in the rewritten `landing.html` includes rules for `.cta-btn`,
  `.card-grid`, `.use-card`, `.flow-diagram`, and `.faq-item`. All rules use only existing
  mctl design tokens (no raw hex values outside the existing fallback block). A
  `@media (max-width: 640px)` block collapses `.card-grid` to a single column and stacks
  the `.flow-diagram` nodes vertically. No existing CSS rules are removed that are still
  used by docs.html (confirm by cross-referencing class names).

- [ ] 5. Update top-bar navigation in both pages
  (depends on 3 and 1)
  DoD: In `landing.html`, the nav `<a href="#tools">tools</a>` and
  `<a href="#scopes" class="hide-sm">scopes</a>` links are replaced with
  `<a href="/docs">docs</a>`. In `docs.html`, the nav contains a `<a href="/">home</a>`
  link and a `<a href="/docs">docs</a>` active indicator (or matching structure). The
  footer in both pages links to `/docs`, `/security`, and `/privacy`. Manual browser test
  of `/` and `/docs` confirms nav links are correct.

- [ ] 6. Verify `security_test.go` still passes and add a smoke test for `/docs`
  (depends on 2)
  DoD: `go test ./internal/web/...` passes with zero failures. Add one test case in
  `internal/web/security_test.go` (or a new `docs_test.go`) that calls the `Docs()`
  handler with a stub `landingData` and asserts: HTTP 200, `Content-Type: text/html`,
  response body contains the string "Available tools" (confirming the tools table rendered).
  The existing `Landing()` handler test (if present) continues to pass; if no test exists
  for `Landing()`, add a parallel assertion that the new landing body contains
  "Your Telegram, inside Claude".

## Tests

- [ ] T1. `go build ./...` passes after all six tasks — confirms `//go:embed` paths
  resolve, templates parse without error, and the new route compiles.
- [ ] T2. `go vet ./...` produces no diagnostics.
- [ ] T3. `go test ./internal/web/...` passes — unit tests for `Docs()` and updated
  `Landing()` handler return HTTP 200 with expected body markers.
- [ ] T4. Manual browser test of `/` (dark theme): hero headline visible, "Add to Claude"
  button present and links to `https://claude.ai/customize/connectors`, three use-case
  cards render, how-it-works diagram visible, trust section visible without warning colour,
  FAQ section visible. No tools table on this page.
- [ ] T5. Manual browser test of `/docs`: connector setup steps present with the correct
  `MCPURL` injected, tools table present (9 rows), scopes table present, storage table
  present, smoke-test curl block present.
- [ ] T6. Manual browser test of `/docs` light theme: accent colours remain legible (WCAG
  AA contrast). The same light-mode darkening rules that exist in landing.html for
  `[data-theme="light"]` must be replicated in docs.html.
- [ ] T7. Responsive check: resize browser to 375 px wide; confirm the card grid in `/`
  collapses to a single column and the flow diagram stacks vertically.
- [ ] T8. Browser navigation from `/` -> `/docs` and `/docs` -> `/` via nav links works.
  Browser navigation to `/security` and `/privacy` from both pages works.

## Rollback

The change touches only static HTML files embedded at compile time and one new route
registration. Rollback procedure:

1. Revert the PR branch (`git revert <merge-commit>` or `git reset --hard` to the pre-merge
   commit on a hotfix branch).
2. Deploy the reverted binary. The embedded HTML reverts atomically with the binary; no
   database migration, no config change, and no infrastructure change is required.
3. The `/docs` route disappears with the reverted binary — existing bookmarks to `/docs`
   return 404. This is acceptable because `/docs` is a new route with no prior bookmarks.
4. The `/` route returns the original developer-focused landing page.

No data loss or session impact is possible from this change; it is purely presentational.
