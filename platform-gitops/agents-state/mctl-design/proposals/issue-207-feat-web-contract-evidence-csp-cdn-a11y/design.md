# Design: issue-207-feat-web-contract-evidence-csp-cdn-a11y

## Current state

Clone of `mctlhq/mctl-design` at `7e1fbb0634d57a9d371e01f487785cd187b362c7` (2026-11-08), root
`package.json` version `0.20.2`.

- **CDN serving contract** `[CODE]` — `nginx.conf`:
  - `location ~ ^/(mctl|global|prose|site)\.css$` (floating sheets): `Access-Control-Allow-Origin: *`,
    `Cache-Control: public, max-age=3600`.
  - `location ~ ^/[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?/(mctl|global|prose|site)\.css$`
    (versioned): `Access-Control-Allow-Origin: *`, `Cache-Control: public, max-age=31536000, immutable`.
  - `/brand/` 1h with CORS; root SVG aliases 1h; generic assets 7d without CORS; SPA fallback for `/`.
  - No `Vary` header is set by nginx; gzip is on for `text/css`, so nginx may add `Vary: Accept-Encoding`
    (`gzip_vary` is not set, so this must be observed, not assumed). Edge/CDN behaviour in front of
    nginx is not described anywhere in the repo.
- **Security headers** `[CODE]` — `security-headers.conf` sets only `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`. There is **no
  Content-Security-Policy** for `ui.mctl.ai` in source; whether an edge adds one is unknown.
- **Published versioned sheets** `[CODE]` — `apps/storybook/public/0.5.0` ... `0.20.2/` are committed;
  `0.20.2` is the current version. `scripts/check-token-version-bump.mjs` keeps these immutable.
  `.prettierignore` excludes `apps/storybook/public/` but not `docs/`, so a new report is subject to
  `pnpm format:check` in `ci.yml`.
- **README consumer guidance** `[CODE]` — `README.md` lines 73-100 still show `0.19.0` URLs in the
  examples, while the version is `0.20.2`; consumers may therefore pin either. This is one reason the
  per-site pinned version must be read from each consumer's source, not from the README.
- **Shared header behaviour contract** `[CODE]` — `packages/css/src/site.css` (`.mctl-site-header`,
  `.mctl-site-burger`, comment at ~line 228): below 768px (981px with `--drawer-wide`) a header with
  `.mctl-site-burger` becomes a right drawer toggled by `data-nav-open`. CSS owns the look only; each
  consumer owns the behaviour (keep `aria-expanded`/`aria-controls` in step, close on Escape, outside
  click, route change and viewport growth, return focus to the burger). Storybook stories in
  `apps/storybook/stories/foundations/SiteHeader.stories.ts` exercise the CSS with play functions and
  axe via `scripts/browser-tests-docker.sh`. `packages/ui/src/components/MNav.vue` exists but the
  public sites consume the CSS classes, not necessarily the Vue component.
- No `docs/` directory exists in the repository today.

Deployed state checked:

- `[CONFIG]` `$MCTL_GITOPS_ROOT/services/admins/mctl-design/values.yaml`: `image.repository
  ghcr.io/mctlhq/mctl-design`, `tag "7e1fbb0634d5"` (string equals the inspected clone
  HEAD prefix); hosts `ui.mctl.ai`, `admins-mctl-design.mctl.ai`. This name match is NOT an
  attestation that the deployed image was built from that commit; the image digest/release-to-source
  provenance join was not checked.
- `services/admins/mctl-web/values.yaml`: tag `7.21.1`; hosts `mctl.ru`, `mctl.ai`;
  `catalog-info.yaml` source-repo `mctlhq/mctl-web`.
- `services/admins/mctl-docs/values.yaml`: tag `0.1.66`; hosts `docs.mctl.ai`, `admins-mctl-docs.mctl.ai`.
- `services/labs/mctl-telegram/values.yaml`: tag `0.137.1`; hosts `tg.mctl.ai`,
  `labs-mctl-telegram.mctl.ai`; contains OAuth redirect allowlists (`OAUTH_ALLOWED_IMPLICIT_HOSTS`),
  confirming auth routes exist that must stay source/preview-only.
- `services/labs/mctl-academy/values.yaml`: tag `0.1.76`; hosts `academy.mctl.ai`, `labs-mctl-academy.mctl.ai`.
- `services/labs/mctl-alice/values.yaml`: tag `2.13.1`; host `alice.mctl.ai`.
- `services/labs/seerrsense/values.yaml`: tag `1.14.1`; hosts `seerrsense.mctl.ai`, `labs-seerrsense.mctl.ai`.
- `[LIVE]` Authenticated `mctl_list_services(team=admins)` and `mctl_list_services(team=labs)`
  (ArgoCD ok, complete true): all seven apps `Synced`, observed images equal GitOps **tag strings**
  (mctl-design `7e1fbb0634d5`, mctl-web `7.21.1`, mctl-docs `0.1.66`, mctl-telegram `0.137.1`,
  mctl-academy `0.1.76`, mctl-alice `2.13.1`, seerrsense `1.14.1`). This proves desired-vs-observed
  tag parity, NOT that the running image matches the inspected source `main` revision. A preview
  app `labs/mctl-telegram-preview` (`tg-preview.mctl.ai`, image `mctl-telegram:main-5fb1de8`)
  exists. Health status was not returned by this call.
- Not checked in this run: source repositories of the six consumers (not cloned), any public HTTP
  response, any CDN/edge configuration. These are gaps, not absences.

## Proposed solution

Add one docs-only file, `docs/evidence/web-contract-evidence.md`, produced by the implementer under
strict read-only rules. No other file changes.

Report structure:

1. **Header block**: date (UTC), mctl-design SHA, run identity, tool availability (HTTP client,
   headless browser: available / `not-run` with reason), and the provenance tag legend
   (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[PREVIEW]`, `unknown (not observed)`).
2. **Parity table** (one row per site + `ui.mctl.ai`): inspected source revision SHA/tag `[CODE]`
   (never label it the deployed revision unless provenance is proved); GitOps desired image tag
   `[CONFIG]`; ArgoCD **observed** image/sync/health `[LIVE]` (authenticated
   `mctl_list_services` / `mctl_get_service_status`); public response build marker, when safely
   observed, `[LIVE]`; and an explicit deployed image-tag-to-source mapping or
   `unknown (not observed)` when build digest, CI attestation or immutable release mapping is not
   available. Record exact `ui.mctl.ai` URLs and/or `@mctlhq/*` versions found in pinned source,
   classified as `0.20.2`, floating or another pin `[CODE]`. Never join source and deployment
   solely by a common-looking tag or a matching short SHA prefix.
3. **HTTP header evidence** `[LIVE]`: for each site's public landing page and for
   `https://ui.mctl.ai/{mctl,global,prose,site}.css` plus `https://ui.mctl.ai/0.20.2/{...}.css`:
   status, redirect chain, CSP / CSP-Report-Only verbatim, Cache-Control, ETag, Last-Modified, Age
   and CDN cache-status headers, ACAO, Vary, and a SHA-256 of each stylesheet body compared with
   `sha256sum apps/storybook/public/0.20.2/*.css` from the pinned clone `[CODE]`. CORS is probed with
   a single `Origin: https://mctl.ai` header on the stylesheet requests only. Each row is diffed
   against `nginx.conf` expectations and divergences are listed (for example, an edge overriding
   `max-age`). Commands are written as copy-paste `curl -sS -D - -o /dev/null --max-redirs 0` lines
   with no cookies.
4. **Sensitive routes** `[CODE]`/`[PREVIEW]` only: per site, list auth/consent/OAuth/error/redirect
   routes and their CSP as declared in pinned source (middleware, server config, meta tags). Live
   rows are explicitly "not requested by policy".
5. **Header behaviour** `[PREVIEW]`: Playwright (same pinned image as
   `scripts/browser-tests-docker.sh`) against (a) mctl-design Storybook `Foundations/Site Header`
   stories built from the pinned SHA, (b) `tg-preview.mctl.ai` public anonymous page, and (c) where
   permitted, the anonymous public landing page of each site at 768px and 981px, read-only. Checks:
   toggle, Enter/Space/Escape, outside pointer, `aria-expanded`, focus return, tab order,
   reduced-motion emulation, JS-disabled context. Each check has observed result, proposed
   acceptance criterion and test status: `observed`, `not-run` (applicable but unexecuted, with
   reason) or `not-applicable` (inapplicable mechanism with pinned source justification). For
   Telegram's CSS-only public navigation, a JS-specific drawer-handler check may be
   `not-applicable`, but user-visible keyboard/focus/no-JS outcomes remain applicable. For Docs'
   VitePress-native menu, mark JS adapter implementation details `not-applicable` only with source
   proof; keep keyboard and focus checks applicable. Do not mask missing tests as N/A. The test
   script itself is quoted as reproduction instructions, not committed as CI.
6. **Evidence/unknown/owner matrix** mapping each claim to provenance tag, observed value or
   unknown, test status (`observed`, `not-run`, or justified `not-applicable`), owner repo and
   existing issue (design#34, design#78, telegram#599, academy#210, gitops#500).
7. **Next gates**: `web-header-a11y-contract` (entry: applicable user-facing header checks
   observed for all six sites or explicit owner-accepted `not-run`, with justified N/A limited to
   inapplicable implementation mechanisms; contract based on `site.css`) and
   `web-asset-integrity-contract` (entry: source CSS pin and supply method known per site; versioned
   body hashes and effective CSP `style-src` verified on CDN-consuming public routes **where HTTP
   was permitted**, otherwise documented `not-run` and a follow-up evidence gate; strict local-
   vendored auth/consent routes remain source/preview-only). Both are proposed for separate human
   decisions; no implementation is started. Missing live proof does not become PASS.

Why here: `mctl-design` owns the CDN contract (`nginx.conf`) and the header CSS contract
(`site.css`), so the evidence sits next to the code it measures; the epic can link it.

## Alternatives

- **Put the report in mctlhq/.github next to the spike report**: keeps epic docs together, but the
  issue asks for `mctl-design/docs/` and the CDN/header contracts live here. Dropped; the epic links it.
- **Add an automated CI/Playwright job that checks live headers**: gives continuous evidence but
  is explicitly out of scope (no CI infrastructure, no production probing in CI). Dropped; the
  script is quoted as reproduction instructions only.
- **Per-site evidence files in each consumer repo**: closer to owners but scatters one baseline over
  six repos and six PRs, contradicting the single first slice. Dropped; owners get matrix rows instead.

## Platform impact

- No migrations, no runtime, image, CSP, CDN or GitOps change. `docs/` is not copied into the
  Storybook image (the `Dockerfile` builds `apps/storybook`), so `ui.mctl.ai` is unaffected.
  The implementer should confirm this from `Dockerfile` before opening the PR.
- CI: `check:token-version` is not triggered (no change under `packages/{tokens,css}`); no version
  bump is needed. `format:check` covers the new Markdown, so it must be Prettier-formatted.
- Risks and mitigations:
  - Live probing triggering edge protection or rate limits: a handful of anonymous `HEAD`/`GET`
    requests, no loops, record `not-run` on any block.
  - Leaking sensitive data into the report: no cookies or credentials are sent; response headers like
    `Set-Cookie` are redacted to their names only; no auth routes are requested live.
  - Treating unknowns as passes: every row requires provenance or an explicit unknown, test
    status and reason. N/A cannot disguise unavailable browser/HTTP execution.
  - Evidence going stale: every row is dated and pinned; the report states it is a point-in-time baseline.
  - Recommending CSP relaxation: forbidden by requirements; findings that would need a looser policy
    are recorded as open questions for the owner, not recommendations.
