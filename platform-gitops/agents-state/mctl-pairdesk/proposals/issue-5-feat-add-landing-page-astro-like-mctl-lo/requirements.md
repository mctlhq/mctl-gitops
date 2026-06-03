# Proposal: Add Astro static landing page at `/`, move Mini App to `/app`

## Context

PairDesk currently has no public-facing landing page. A browser visitor who opens
`labs-mctl-pairdesk.mctl.ai` sees the React Mini App shell, which requires a Telegram
WebApp context to function — resulting in a blank or broken experience for anyone not
arriving through the bot. There is also no place on the public web that explains what
PairDesk is, how to join, or how to find the bot.

`mctl-loyalty` solves the same problem with an Astro static landing at `/` and the Mini
App at `/app`. PairDesk should adopt the same pattern: an Astro-built, fully static HTML
page at the root URL that explains the service, directs visitors to the Telegram bot, and
does not require JavaScript or authentication. The React Mini App moves to `/app`, which
is already the value stored in `MINI_APP_URL` in
`platform-gitops/services/labs/mctl-pairdesk/values.yaml`.

## User stories

- AS a prospective community member I WANT to open `labs-mctl-pairdesk.mctl.ai` in a
  browser and immediately understand what PairDesk does SO THAT I can decide whether to
  apply to join.
- AS a prospective community member I WANT a clearly visible link or button that takes me
  directly to the PairDesk Telegram bot SO THAT I can start the join flow without
  searching for the bot.
- AS an existing community member I WANT the Mini App to be stable and accessible at
  `/app` SO THAT any bookmarks or bot deep-links I have continue to work after the
  landing page is added.
- AS a platform operator I WANT `MINI_APP_URL` to point to `/app` (already the case in
  the current values.yaml) SO THAT bot-generated "Open PairDesk" buttons open the
  correct path.
- AS a platform operator I WANT the static landing page to be built and served by the
  existing Express process (no new infrastructure) SO THAT the deployment surface stays
  unchanged.

## Acceptance criteria (EARS)

### Landing page — content and availability
- WHEN a browser sends `GET /` to the Express server THE SYSTEM SHALL respond with
  HTTP 200 and a `text/html` document that is the Astro-generated landing page.
- WHEN the landing page is rendered THE SYSTEM SHALL display a brief description of
  PairDesk as a closed P2P bulletin board (not an exchange; no custody, no payments).
- WHEN the landing page is rendered THE SYSTEM SHALL display clear instructions for
  joining: open the bot, send `/start`, wait for admin approval.
- WHEN the landing page is rendered THE SYSTEM SHALL include a Telegram deep-link CTA
  button (anchor to `https://t.me/<bot_username>`) that opens the bot.
- WHILE the landing page is loaded THE SYSTEM SHALL function correctly with JavaScript
  disabled (the page is static HTML/CSS; no client-side JS framework).
- WHEN the landing page is served THE SYSTEM SHALL use the "Direction C — Trust /
  Banking" visual language: deep blue accent (`#2f6bf6`), clean typography, and tokens
  from `web/src/pairdesk-tokens.css` adapted for a public-web context (no `--tg-*`
  fallbacks needed).
- WHEN a search engine crawler requests `/` THE SYSTEM SHALL return a fully rendered
  HTML document (no client-side rendering required for content visibility).

### Mini App path change
- WHEN a browser or Telegram WebApp sends `GET /app` THE SYSTEM SHALL respond with
  HTTP 200 and the React Mini App entry HTML (`public/app/index.html`).
- WHEN a browser sends `GET /app/<any-subpath>` THE SYSTEM SHALL respond with HTTP 200
  and the same React Mini App entry HTML (SPA client-side routing fallback).
- WHILE the Mini App is running at `/app` THE SYSTEM SHALL behave identically to its
  current behaviour at `/` — all `/api/*`, `/telegram/webhook`, `/healthz`, and
  `/readyz` routes are unaffected.
- WHEN the `MINI_APP_URL` environment variable is set to
  `https://labs-mctl-pairdesk.mctl.ai/app` THE SYSTEM SHALL embed that URL in bot
  messages that include a web_app button (behaviour unchanged from current config).

### Build and deployment
- WHEN the Docker image is built THE SYSTEM SHALL include both the Astro landing page
  (at `public/index.html` and `public/_astro/`) and the React Mini App SPA (at
  `public/app/`).
- WHEN `npm run build` is executed locally THE SYSTEM SHALL produce both the landing
  page and the SPA in the correct output locations without one overwriting the other.
- IF the `landing/` Astro build fails THE SYSTEM SHALL fail the CI `landing` job and
  block the PR merge.
- WHEN the Docker image build stage for the landing runs THE SYSTEM SHALL only copy
  `landing/` sources into that stage (no access to `web/` sources, and vice versa).

## Out of scope

- Authentication or OAuth of any kind on the landing page — it is fully public.
- Cloudflare Worker or edge delivery — Express serves static files directly, same as
  the current Mini App build.
- Bot username configuration as a new env var — the Telegram deep-link is a static
  string in the Astro source (see Open Questions).
- Changes to any backend API routes, database schema, or domain logic.
- Multi-community support — the landing is for the single MVP community.
- Internationalisation — English only.
- The platform-gitops `values.yaml` update — `MINI_APP_URL` is already set to
  `https://labs-mctl-pairdesk.mctl.ai/app` in the current file (verified in the repo);
  no gitops change is required.

## Open questions

1. **Bot username for the deep-link CTA.** The issue asks for a "Bot link / Telegram
   deep-link button" but does not state the bot's `@username`. The existing codebase has
   no `TELEGRAM_BOT_USERNAME` env var; only the token is stored in Vault. The
   implementer should hard-code the known username in the Astro source (or add a build-
   time env var `PUBLIC_BOT_USERNAME` read by Astro) and confirm the username with the
   platform team before publishing. Reasonable default: derive from
   `labs-mctl-pairdesk`'s Vault secret or BotFather record.

2. **Astro output root vs. subdirectory.** The issue text says "Astro builds to
   `public/landing/`", but serving the landing at `/` without extra Express routing
   requires the Astro `outDir` to be `../public` (the root) so that
   `public/index.html` exists and is served automatically by `express.static`. If
   `outDir` is `../public/landing/`, an explicit `GET /` → sendFile handler must be
   added to `src/server.ts`. This proposal recommends `outDir: '../public'` (cleanest
   path, zero extra routing), but the implementer should verify against the loyalty repo
   convention and document the choice.

3. **`/admin` and `/docs` SPA fallback routes.** `src/server.ts` currently maps
   `/admin`, `/admin/*`, `/docs`, `/docs/*` to the SPA's `index.html`. After the SPA
   moves to `public/app/index.html`, these fallbacks should be retained and point to
   `public/app/index.html`. Confirm that no future landing sub-page will conflict with
   these paths.
