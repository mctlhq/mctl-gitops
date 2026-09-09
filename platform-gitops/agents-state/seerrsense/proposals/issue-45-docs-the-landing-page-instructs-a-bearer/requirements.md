# Split the documentation by audience: landing page for the person who signs in, README for the person who runs the server

## Context

The hosted SeerrSense landing page (`public/index.html`) still instructs a
newcomer to hand their MCP client "the bearer token you were issued" and shows a
JSON snippet containing `"Authorization": "Bearer <your token>"`
(`public/index.html:200-223`). On the hosted deployment the shared token is
switched off (`SEERRSENSE_LEGACY_TOKEN_ENABLED=false`), and the code path that
reads it is skipped entirely in that case (`src/auth/config.ts:66-68`). An OAuth
client obtains its token through the authorization code flow
(`src/auth/routes.ts:273-506`) and never sends a hand-copied header. The very
first instruction on the page therefore cannot be followed.

The same page also mixes two audiences. "Connecting to Seerr"
(`public/index.html:176-198`) tells a *user* to sign in at `/account`, and in the
next card tells them to set `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` and
`NEBIUS_API_KEY` — operator environment variables parsed in
`src/core/config.ts:19-22`, which a hosted user cannot set and does not need,
because the Cloudflare Access credentials are two form fields on `/account`
(`public/account.html:70-79`, stored via `src/api/account.ts:64-124`). The
"Questions" section (`public/index.html:241-258`) describes access as a bearer
token plus "an explicit list of addresses", which stops being true once #44 opens
signup, and ends with a self-hosting answer. Meanwhile `README.md` — the natural
home for all the operator material — has `## Quick Start` (`README.md:86-87`),
`## MCP` (`README.md:121-122`), `## REST API` (`README.md:185-186`),
`## Architecture` (`README.md:188-189`), `## Development` (`README.md:233-234`),
`## Deployment` (`README.md:236-237`) and `## Roadmap` (`README.md:239-240`) all
reading `*TBD*`. Only `## Configuration` (`README.md:89-119`), `## Whose Seerr`
(`README.md:124-153`), `## Web` (`README.md:155-183`) and `## Security Model`
(`README.md:191-231`) carry real prose.

This matters now because #44 opens signup to anyone with a Google account. The
landing page is the first thing a newcomer sees, and its first instruction is
impossible to follow. This proposal is documentation-only: no runtime behaviour,
no route, no schema and no environment variable changes.

## User stories

- AS a person who wants to use the hosted SeerrSense I WANT the landing page to
  give me three ordered steps — add the connector, sign in, attach my Seerr — SO
  THAT I can reach a working `resolve_media` without asking anyone.
- AS a person adding the connector in claude.ai or ChatGPT I WANT the exact menu
  path for my client SO THAT I do not have to guess where custom MCP connectors
  live in that product.
- AS a newcomer I WANT the page to never mention a bearer token or an
  environment variable SO THAT I am not sent down a path the hosted server does
  not support.
- AS somebody who wants to run SeerrSense themselves I WANT `README.md` to
  document Quick Start, MCP, REST API, Architecture, Development and Deployment
  SO THAT the operator material I used to find on the marketing page has a real
  home.
- AS a maintainer I WANT `tests/landing.test.ts` to assert the absence of the
  removed strings and the presence of the new steps SO THAT the page cannot
  regress into instructing a token that does not exist.
- AS a signed-in person reading `/account` I WANT the intro not to promise a
  "shared" instance SO THAT the text stays true once #44 restricts the household
  instance to listed owners.

## Acceptance criteria (EARS)

Landing page (`public/index.html`)

- WHEN `GET /` is served THE SYSTEM SHALL return a page whose body contains
  neither the string `Authorization: Bearer` nor `Bearer <your token>` nor
  `Bearer &lt;your token&gt;`.
- WHEN `GET /` is served THE SYSTEM SHALL return a page containing none of the
  strings `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`, `NEBIUS_API_KEY`,
  `SEERRSENSE_AUTH_TOKEN` or `SEERR_API_KEY`.
- WHEN `GET /` is served THE SYSTEM SHALL return a page containing a single
  setup section carrying three numbered steps, in this order: add the connector
  to the assistant, sign in with Google, attach your own Seerr at `/account`.
- WHEN the setup section is rendered THE SYSTEM SHALL name both client paths
  verbatim: for claude.ai `Customize`, `Connectors`, `Add custom connector`; for
  ChatGPT `Settings`, `Security and login`, `Developer mode`, then `Plugins`.
- WHILE the setup section exists THE SYSTEM SHALL keep it reachable at the
  anchor the top bar links to, so the `Setup` link in `public/index.html:46`
  resolves to a real element on the page.
- WHEN the setup section is rendered THE SYSTEM SHALL state that Google sign-in
  happens on the first `Connect`, that claude.ai Free allows one custom
  connector while Pro and Max are unrestricted, that on Team and Enterprise an
  owner adds it under organization settings, and that ChatGPT support is web
  only on Plus, Pro, Business, Enterprise and Education.
- WHEN the "attach your Seerr" step is rendered THE SYSTEM SHALL link to
  `/account`, name where the Overseerr API key is found (Settings, then General,
  then API Key), and say the credentials are tested before they are saved,
  matching `src/api/account.ts:93-102`.
- IF a reader has not yet attached a Seerr THEN THE SYSTEM SHALL have told them
  on the page that the tools will point them at `/account`, consistent with
  `notConnectedMessage` in `src/providers/seerr/tenants.ts:106-109`.
- WHILE the page is served THE SYSTEM SHALL keep the hero
  (`public/index.html:59-77`), the endpoint element `#mcp-url`, the
  `Copy MCP URL` button `#copy-url`, and the `MCP tools` section
  (`public/index.html:139-174`) intact.
- WHEN the page script runs THE SYSTEM SHALL still derive the endpoint from
  `window.location.origin + "/mcp"` and fill `#mcp-url` and every
  `.mcp-url-slot`, so removing the JSON snippet does not break the copy control.
- WHEN the "Questions" section is rendered THE SYSTEM SHALL contain exactly the
  three user-facing entries — does it replace Overseerr or Jellyseerr, can an
  assistant request on its own, does a language model see my library — and SHALL
  NOT contain "How is access controlled?" or "Can I self-host it?".
- WHILE the page is served THE SYSTEM SHALL depend on no third-party stylesheet:
  `/assets/tokens.css` and `/assets/components.css` stay vendored and no
  `ui.mctl.ai` URL appears, so the existing assertions at
  `tests/landing.test.ts:80-90` keep passing.
- WHEN CI runs THE SYSTEM SHALL keep `npm run check:tokens` passing, since
  `public/assets/tokens.css` is not touched by this change.

Account page (`public/account.html`)

- WHEN the signed-out intro at `public/account.html:42-44` is rendered THE
  SYSTEM SHALL NOT claim the person's instance is used "instead of the shared
  one", and SHALL instead state that SeerrSense searches and requests on that
  instance.

README (`README.md`)

- WHEN `README.md` is read THE SYSTEM SHALL contain no occurrence of the literal
  `*TBD*`.
- WHEN `## Quick Start` is read THE SYSTEM SHALL document the container path
  (the `Dockerfile` image, `EXPOSE 8787`, the `/healthz` healthcheck), the
  standalone binary path (the four artifacts built by
  `.github/workflows/release-binaries.yml:26-32`), and `seerrsense stdio`
  (`src/index.ts:9-19`), together with the minimum settings a bare install needs
  — `SEERR_URL`, `SEERR_API_KEY`, `SEERRSENSE_AUTH_TOKEN` — as enforced by
  `assertHttpConfig` in `src/core/config.ts:35-40`.
- WHEN `## MCP` is read THE SYSTEM SHALL name the `/mcp` endpoint, the four
  tools registered in `src/mcp/server.ts`, the three scopes from
  `src/auth/config.ts:15-18`, the four `.well-known` discovery documents served
  at `src/auth/routes.ts:255-271`, Client ID Metadata Documents, and the
  pre-registered client form of `SEERRSENSE_OAUTH_CLIENTS`.
- WHEN `## MCP` or `## Configuration` is read THE SYSTEM SHALL carry the
  Cloudflare Access and Nebius operator material removed from the landing page,
  adjacent to the Configuration table that already lists those variables
  (`README.md:97-99`).
- WHEN `## REST API` is read THE SYSTEM SHALL list the four endpoints declared
  in `src/api/server.ts:285-360` — `GET /api/v1/search`,
  `GET /api/v1/media/:mediaType/:tmdbId`, `POST /api/v1/request`,
  `GET /api/v1/resolve` — and the three account endpoints in
  `src/api/account.ts:49,64,127`, noting that the account endpoints authenticate
  with the session cookie and not an MCP access token.
- WHEN `## Architecture` is read THE SYSTEM SHALL describe the real module
  layout: `src/api`, `src/auth`, `src/core`, `src/mcp`, `src/providers/seerr`,
  and the tenant resolution order implemented by `TenantResolver`
  (`src/providers/seerr/tenants.ts:44-102`).
- WHEN `## Development` is read THE SYSTEM SHALL document the scripts actually
  present in `package.json` — `dev`, `build`, `typecheck`, `test`,
  `sync:tokens`, `check:tokens` — and the CI gate order in
  `.github/workflows/ci.yml`, including `TEST_DATABASE_URL`.
- WHEN `## Deployment` is read THE SYSTEM SHALL describe the container build and
  the release-please plus release-binaries tag flow.
- IF a `*TBD*` heading has nothing true to say THEN THE SYSTEM SHALL delete the
  heading rather than leave the placeholder; this applies in particular to
  `## Roadmap` (`README.md:239-240`).
- WHILE this change is in flight THE SYSTEM SHALL keep `## Whose Seerr`
  (`README.md:124-153`) consistent with #44's household model; whichever of the
  two lands second rebases onto the first.

Tests (`tests/landing.test.ts`)

- WHEN the new assertions are run against the page as it exists today THE SYSTEM
  SHALL fail, proving the test actually guards the change.
- WHEN the new assertions are run against the rewritten page THE SYSTEM SHALL
  pass, and every existing case in `tests/landing.test.ts:26-203` SHALL keep
  passing unchanged.

## Out of scope

- Any runtime, route, schema or environment-variable change. This proposal edits
  `public/index.html`, `public/account.html`, `README.md` and
  `tests/landing.test.ts` only.
- Implementing open signup itself. That is #44; this proposal only stops the
  page from describing the allowlist that #44 replaces.
- Rewriting `README.md:191-231` (`## Security Model`), which still asserts
  "Access is an allowlist, `SEERRSENSE_ALLOWED_EMAILS`, and it fails closed".
  That sentence becomes stale when #44 lands and is #44's to update.
- `public/privacy.html` and `public/terms.html`, which are legally reviewed text
  and are guarded by `tests/landing.test.ts:182-191`.
- Re-vendoring `public/assets/tokens.css` or editing
  `public/assets/components.css` beyond what a new step list requires; `.steps`
  already exists at `public/assets/components.css:364-374`.
- Localisation, screenshots and a video walkthrough of the connector flow.

## Open questions

- **Vendor UI drift.** The claude.ai and ChatGPT menu paths were verified
  against vendor documentation on 2026-09-09 per the issue. Both products change
  their settings layout often; the page will carry a stale path eventually and
  there is no test that can catch it. Proceeding as specified, and recording the
  verification date in an HTML comment next to the steps so a future reader
  knows how old the claim is.
- **Anchor id.** The top bar links to `#setup` (`public/index.html:46`) and the
  section is `id="setup"` (`public/index.html:200`). Proceeding by keeping the
  id `setup` on the new three-step section so the nav link, and any external
  link to `https://seerrsense.mctl.ai/#setup`, keeps working. Reviewer should
  confirm they do not prefer a rename.
- **"What it adds to the Seerr stack".** The issue says drop it "if the hero
  already says it". The hero (`public/index.html:62-66`) states the premise but
  not the three guarantees in the cards, one of which — the write guard — is the
  page's only mention of why `request_media` is safe. Proceeding by keeping the
  section and tightening it to two cards, folding "Your server, your rules" into
  the new step 3. Reviewer may prefer full removal.
- **"How a request travels".** Proceeding by keeping it: `.flow-scroll` is
  asserted at `tests/landing.test.ts:159-169`, so deleting it would require
  editing an unrelated existing test.
- **Standalone binary and `public/`.** `publicDir` is resolved relative to the
  compiled module (`src/api/server.ts:173`), while the bun-compiled binary
  bundles only `src/index.ts`. Whether a released binary serves `/` at all is
  unverified in this clone. Proceeding by documenting the binary primarily for
  `seerrsense stdio` in `## Quick Start`, and adding a task to verify the HTTP
  case before making a stronger claim.
- **README line drift.** The issue cites `README.md:139-145` for "Whose Seerr";
  in this clone that section spans `README.md:124-153`. Line numbers in the
  issue are approximate and the section headings are authoritative.
