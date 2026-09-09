# Tasks: issue-45-docs-the-landing-page-instructs-a-bearer

- [ ] 1. Write the two new failing cases in `tests/landing.test.ts` first, inside
      the existing `describe("landing page")` block, using the same
      `app.inject({ method: "GET", url: "/" })` shape as the cases above them:
      one forbidding `Authorization: Bearer`, `Bearer &lt;your token&gt;`,
      `bearer token`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`,
      `NEBIUS_API_KEY`, `SEERRSENSE_AUTH_TOKEN` and `SEERR_API_KEY`; one
      requiring `id="setup"`, the strings `Add custom connector`,
      `Developer mode` and `Settings, then General, then API Key`, and the three
      step headings in `indexOf` order (connector, then sign-in, then Seerr).
      Do not add `Bearer` unqualified and do not forbid `seerr:read` /
      `seerr:request` — `tests/landing.test.ts:32` requires the latter present.
      — DoD: `npm test` runs and exactly these two new cases fail against the
      unmodified `public/index.html`; every pre-existing case at
      `tests/landing.test.ts:26-203` still passes. Paste the failing output into
      the PR description.

- [ ] 2. Rewrite the setup section of `public/index.html` (depends on 1).
      Delete `public/index.html:176-198` ("Connecting to Seerr") and
      `public/index.html:200-223` ("Set it up"); put one section with
      `id="setup"` in their place, using the existing `.steps` list
      (`public/assets/components.css:364-374`), carrying three `<li>`:
      (a) add the connector, with the claude.ai path *Customize → Connectors →
      "+" → Add custom connector* including the Free / Pro-Max / Team-Enterprise
      note, and the ChatGPT path *Settings → Security and login → Developer
      mode*, then *Plugins → "+"*, web only on Plus, Pro, Business, Enterprise
      and Education, and the MCP URL in a `<code class="mcp-url-slot">`;
      (b) sign in with Google on the first *Connect*, one consent screen, nothing
      to copy — phrased without the words "bearer token";
      (c) attach your Seerr at `/account`: address, API key from *Overseerr →
      Settings → General → API Key*, and the two Cloudflare Access **fields**
      only if the instance sits behind Access, plus the fact that the page tests
      the credentials before saving (`src/api/account.ts:93-102`) and that the
      tools point at `/account` if this step is skipped
      (`src/providers/seerr/tenants.ts:106-109`).
      Add an HTML comment recording that the vendor paths were verified
      2026-09-09.
      — DoD: both cases from task 1 pass; the page contains no environment
      variable name and no mention of a token; `#setup` still resolves for the
      top-bar link at `public/index.html:46`; at least one `.mcp-url-slot`
      remains so `public/index.html:300-302` still has a target.

- [ ] 3. Trim the surrounding sections of `public/index.html` (depends on 2).
      Reduce "What it adds to the Seerr stack" (`:79-106`) to two cards — keep
      "Resolution, not just search" and "Writes are guarded", drop "Your server,
      your rules" now that step 3 covers it. Reduce "Questions" (`:225-260`) to
      the three user-facing entries (replaces Overseerr/Jellyseerr, assistant
      requesting on its own, does a model see my library); delete "How is access
      controlled?" (`:241-247`) and "Can I self-host it?" (`:254-258`), replacing
      the latter with a single README link in the footer row
      (`public/index.html:264-269`). Leave the hero, "How a request travels" and
      "MCP tools" untouched.
      — DoD: `npm test` green with no edit to any pre-existing test case;
      `class="flow-scroll"` and `class="table-scroll"` still present for
      `tests/landing.test.ts:159-170`; the page still contains `seerr:request`
      for `tests/landing.test.ts:32`.

- [ ] 4. Fix the `/account` intro. In `public/account.html:42-44` replace
      "instead of the shared one" so the sentence reads that SeerrSense searches
      and requests on that instance, and stops there. Change nothing else on the
      page.
      — DoD: the string "instead of the shared one" no longer appears in
      `public/`; `tests/account.test.ts` still passes.

- [ ] 5. Fill `## Quick Start` and `## MCP` in `README.md` (replacing the `*TBD*`
      at `README.md:87` and `README.md:122`). Quick Start covers the container
      (`Dockerfile`, port 8787, `/healthz` healthcheck), the standalone binaries
      from `.github/workflows/release-binaries.yml:26-32`, and `seerrsense stdio`
      (`src/index.ts:9-19`), naming `SEERR_URL`, `SEERR_API_KEY` and
      `SEERRSENSE_AUTH_TOKEN` as the minimum, with the last required in HTTP mode
      only per `assertHttpConfig` (`src/core/config.ts:35-40`). MCP covers the
      `/mcp` endpoint, the four tools, the three scopes
      (`src/auth/config.ts:15-18`), the four `.well-known` documents
      (`src/auth/routes.ts:255-271`), Client ID Metadata Documents and the
      `SEERRSENSE_OAUTH_CLIENTS` pre-registration form, cross-linking
      `## Security Model` instead of restating it.
      — DoD: both headings carry real prose; every command, path, port and
      variable named is verifiable against a file cited here; no `*TBD*` remains
      under either heading.

- [ ] 6. Verify whether a bun-compiled binary serves `/` before Quick Start
      claims it (depends on 5). `publicDir` is resolved from the module path at
      `src/api/server.ts:173` while the release build compiles `src/index.ts`
      alone. Either confirm the binary serves the page with `public/` alongside
      it, or state in `## Quick Start` that the binary is for `seerrsense stdio`
      and that HTTP mode needs `public/` present.
      — DoD: `## Quick Start` makes one claim about the binary and that claim was
      checked, with the check recorded in the PR description.

- [ ] 7. Move the operator material into `README.md` (depends on 5). Add a short
      subsection immediately after the Configuration table (`README.md:89-119`)
      covering Cloudflare Access (`CF_ACCESS_CLIENT_ID` /
      `CF_ACCESS_CLIENT_SECRET`, and that a signed-in person supplies the
      per-user equivalent on `/account`) and the optional Nebius semantic layer
      (`NEBIUS_API_KEY`, `NEBIUS_MODEL`), i.e. the content deleted from
      `public/index.html:187-196`.
      — DoD: both topics documented next to the table that already names the four
      variables; no duplicate table row added.

- [ ] 8. Fill `## REST API`, `## Architecture`, `## Development` and
      `## Deployment` in `README.md` (replacing `*TBD*` at `:186`, `:189`,
      `:234`, `:237`). REST API lists `GET /api/v1/search`,
      `GET /api/v1/media/:mediaType/:tmdbId`, `POST /api/v1/request`,
      `GET /api/v1/resolve` (`src/api/server.ts:285-360`) and the three
      `/api/v1/account/connection` methods (`src/api/account.ts:49,64,127`),
      noting the session-cookie audience split already argued at
      `README.md:131-135`. Architecture maps `src/api`, `src/auth`, `src/core`,
      `src/mcp`, `src/providers/seerr` and the `TenantResolver` order
      (`src/providers/seerr/tenants.ts:44-102`) with its one-minute cache and the
      `forget()` call at `src/api/account.ts:117`. Development lists the six
      `package.json` scripts and the CI gate order in
      `.github/workflows/ci.yml`, including `TEST_DATABASE_URL`. Deployment
      covers the container build, release-please and the tag-triggered binary
      release.
      — DoD: four headings with real prose; every endpoint, script and file path
      exists in the repo.

- [ ] 9. Delete the `## Roadmap` heading and its `*TBD*` (`README.md:239-240`)
      (depends on 8) — there is no roadmap in the repo to describe, and the issue
      asks for the heading to go rather than stay empty.
      — DoD: `grep -c "TBD" README.md` returns 0 and `## Roadmap` is gone.

- [ ] 10. Final consistency pass (depends on 3, 4, 9). Confirm the landing page,
      `/account` and the README tell one story: the page never names a variable
      or a token, the README owns every operator topic the page dropped, and
      `## Whose Seerr` (`README.md:124-153`) and `## Security Model`
      (`README.md:191-231`) were not edited — those belong to #44. If #44 has
      already merged, rebase onto it and reconcile the household wording rather
      than re-editing it here.
      — DoD: `npm run typecheck`, `npm test` and `npm run check:tokens` all
      green; PR description states explicitly which README sections were
      deliberately left to #44.

## Tests

- [ ] T1. New case in `tests/landing.test.ts`: `GET /` contains none of
      `Authorization: Bearer`, `Bearer &lt;your token&gt;`, `bearer token`,
      `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`, `NEBIUS_API_KEY`,
      `SEERRSENSE_AUTH_TOKEN`, `SEERR_API_KEY`. Must fail on today's page
      (`public/index.html:189,194,211`).
- [ ] T2. New case in `tests/landing.test.ts`: `GET /` contains `id="setup"`,
      `Add custom connector`, `Developer mode`, `Settings, then General, then API
      Key`, and the three step headings in `indexOf` order. Must fail on today's
      page.
- [ ] T3. Regression: every pre-existing case at `tests/landing.test.ts:26-203`
      passes with no edit — in particular `seerr:request` present (`:32`),
      `window.location.origin + "/mcp"` present (`:113-116`), `.flow-scroll` and
      `.table-scroll` present (`:159-170`), no `ui.mctl.ai` (`:85`), and the
      `/privacy` and `/terms` links (`:193-197`).
- [ ] T4. `npm run check:tokens` passes: `public/assets/tokens.css` is untouched
      and the page still loads no external stylesheet.
- [ ] T5. `npm run typecheck` and the full `npm test` suite pass, including
      `tests/account.test.ts` after the `public/account.html` wording change.
- [ ] T6. Review check (not automated): `grep -n "TBD" README.md` returns
      nothing.
- [ ] T7. Manual, after #44 is deployed: a second Google account whose address is
      on no list follows the page top to bottom and ends with a working
      `resolve_media` against its own Seerr, without asking anyone. Record which
      client was used and where, if anywhere, the wording was ambiguous.

## Rollback

Documentation-only: four files change (`public/index.html`,
`public/account.html`, `README.md`, `tests/landing.test.ts`) and nothing under
`src/`. Reverting the merge commit restores the previous page and README exactly;
no data is written, no migration runs, no environment variable is read or
written differently, so a revert needs no coordination with the database or with
issued tokens.

Operationally the page is a static file copied into the image
(`Dockerfile:20-21`) and served from disk (`src/api/server.ts:173-186`), so a
rollback is an ordinary redeploy of the previous image tag — the assets carry a
five-minute `max-age` (`src/api/server.ts:184-185`), so a browser holding the new
page pairs with the old stylesheet for at most that long, and the stylesheets are
unchanged by this proposal anyway.

Partial rollback is available if the vendor menu paths turn out wrong: revert
task 2's step 1 copy alone, keeping the token removal and the README work, since
the forbidden-string test (T1) does not depend on the specific vendor wording.
