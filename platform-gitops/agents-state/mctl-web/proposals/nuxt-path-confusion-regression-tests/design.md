# Design: nuxt-path-confusion-regression-tests

## Current state
`deploy.yml` in this repo builds the Nuxt site and deploys the Worker via wrangler (see `context/architecture.md`). Routes: `/`, `/docs`, `/privacy`; Worker on `mctl.ai/api/*` with per-endpoint rate limits. There are no routing-normalization tests today (to confirm).

## Proposed solution
Add a small script (e.g. `scripts/path-smoke.mjs`, Node built-in `fetch`) and a CI step in `deploy.yml` between build and deploy:
1. Serve the built output locally (static server or `nuxt preview`) and run the Worker locally (`wrangler dev` with stub secrets and mocked upstreams).
2. Table-driven requests: for each of `/`, `/docs`, `/privacy` try `//x`, `//docs`, `/docs/`, `/%2e/docs`, `/docs%2F`, and similar; assert status and body equals the canonical page, a redirect, or 404.
3. For `/api/*`, send canonical vs variant paths to a rate-limited endpoint and assert identical routing and that the limit counter is shared (variant requests count toward the limit).
4. Assert error responses contain no stack or internal markers.
Raw paths must be sent unnormalized (use `http`/`undici` with literal paths, since `fetch` normalizes some).
Failures exit non-zero and block deploy. Expected values are stored in one table so they can be adjusted after the Nuxt upgrade.

## Alternatives
- Manual periodic checks: dropped, not repeatable.
- Full E2E framework (Playwright): dropped, heavy for a three-page static site.
- Rely on Nuxt upstream tests: dropped, they do not cover our Worker or deployment topology.

## Platform impact
- Migrations: none.
- Backward compatibility: adds a gate to deploy; a false positive blocks deploy (mitigate with a clear failure report and an easy table edit).
- Resource impact: CI minutes only, no runtime change; `labs` unaffected.
- Risks and mitigations: local Worker differs from Cloudflare edge normalization (also run against staging if available; document the gap); unverified CVE details (use them only as test motivation, not as claims); test flakiness from rate-limit state (reset between runs by using a fresh `wrangler dev` instance).
