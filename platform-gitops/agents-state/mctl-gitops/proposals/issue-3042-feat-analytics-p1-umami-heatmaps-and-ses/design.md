# Design: issue-3042-feat-analytics-p1-umami-heatmaps-and-ses

## Current state

Umami runs as tenant service `admins/umami` on chart `base-service`. Its
config is `platform-gitops/services/admins/umami/values.yaml`:

- Image `ghcr.io/umami-software/umami:3.4.0@sha256:85909afc...`, pinned by
  hand (`mctl.me/auto-deploy: "false"` in `catalog-info.yaml`).
- `TRACKER_SCRIPT_NAME: insights.js` and `CLIENT_IP_HEADER:
  cf-connecting-ip`. `COLLECT_API_ENDPOINT` is deliberately unset, because
  setting it makes Umami write to its read-only root and crash with EROFS.
- The main `ingress` serves `stats.mctl.ai` and `admins-umami.mctl.ai` with
  `forwardAuth.enabled: true` (Backstage
  `/api/oidc-provider/forward-auth?tenant=admins&service=umami`). The alias
  is registered in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-portal.yaml`
  (`host: stats.mctl.ai`, line ~598).
- `extraIngresses` opens exactly two anonymous paths on `stats.mctl.ai`:
  `admins-umami-tracker` (`/insights.js`, `pathType: Exact`) and
  `admins-umami-collect` (`/api/send`, `Exact`). Each is pinned with
  `traefik.ingress.kubernetes.io/router.priority: "1000"` and has no
  middleware. The chart's extra-ingress loop
  (`platform-gitops/helm-charts/base-service/templates/ingress.yaml`) merges
  `$ing.annotations` and sets `router.middlewares` only when
  `$ing.forwardAuth.enabled`. A caller can therefore attach its own
  middleware through the annotation.
- `extraObjects` holds two things. The first is the PostSync Job
  `admins-umami-seed-websites`, which upserts six websites with fixed IDs:
  mctl.ai `3735c207-...`, tg.mctl.ai `d4fa9d69-...`, docs, alice, academy and
  seerrsense. It uses `ON CONFLICT (website_id) DO UPDATE SET domain, name`
  only. The second is the CronJob `admins-umami-retention` (`23 4 * * *`).
  It already deletes `session_replay` and `heatmap_event` rows, but on the
  general **2-year** cut-off, and it fails if anything older survives. Its
  comment treats saved replays as configuration, and
  `session_replay_saved` is not touched.
- Alerts `UmamiRetentionStale` and `UmamiRetentionJobFailed` are in
  `platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml`
  (group `mctl.umami-retention`).
- There is an existing Traefik `Middleware` pattern in `extraObjects`:
  `rateLimit` with `sourceCriterion.requestHeaderName: CF-Connecting-IP` in
  `platform-gitops/services/redloop/redloop-synthetic-staging/values.yaml`,
  and the deny-allowlist middleware in
  `platform-gitops/services/labs/mctl-telegram/values.yaml`. The installed
  CRD group is `traefik.io/v1alpha1` (Traefik v3.7).
- `stats.mctl.ai` is reserved for tenant `admins` in
  `platform-gitops/bootstrap/values.yaml` (`reservedPlatformHosts`).
- No CSP or `frame-ancestors` for mctl.ai is set in this repository
  (searched `platform-gitops` for `content-security-policy`,
  `frame-ancestors`, `customFrameOptions`). Page headers are owned by the
  site repos.

What upstream Umami v3.4.0 does (read from tag `v3.4.0` on GitHub):

- `package.json`: `build:recorder` runs `rollup.recorder.config.js`, which
  builds `src/recorder/index.js` into `public/recorder.js` and replaces
  `__COLLECT_API_HOST__` from `COLLECT_API_HOST`. Dependencies:
  `rrweb ^2.0.1`, `rrweb-player 2.0.0-alpha.20`.
- `src/recorder/index.js`:
  - Reads `data-website-id` (required) and `data-host-url`.
  - Fetches `GET {host}/api/websites/{website}/recorder`.
  - Posts both replay chunks (`type:'record'`) and heatmap batches
    (`type:'heatmap'`) to `POST {host}/api/record`.
  - Needs `x-umami-cache` from `window.umami.getSession().cache` and polls
    about 5 s for it.
  - rrweb options: `maskAllInputs: true`, `maskTextSelector: '*'` only for
    `maskLevel: 'strict'`, the optional `blockSelector`,
    `recordCanvas: false`, `recordCrossOriginIframes: false`,
    `inlineStylesheet: true`, `checkoutEveryNms: 30000`.
  - Heatmap click and scroll events carry `url: location.href`, with query
    and fragment.
  - It wraps `pushState` and `replaceState` and listens for `popstate` only
    when heatmaps are on, and emits `addCustomEvent('url-change', {url})`
    into the replay.
  - It has **no** consent hook, **no** public stop API (only an internal
    `stopReplay` when `maxDuration` is exceeded), **no**
    path/domain/Do-Not-Track exclusion, and **no** URL stripping.
- `src/app/api/websites/[websiteId]/recorder/route.ts`: exports `GET` and
  `OPTIONS` with `skipAuth: true`, so it is public by website ID. It sends
  `Cache-Control: public, max-age=60` and returns `{enabled:false}` unless
  `recorderEnabled` is set. Otherwise it returns `replayEnabled`,
  `heatmapEnabled`, `sampleRate`, `heatmapSampleRate`, `maskLevel`,
  `maxDuration` and `blockSelector`. There is no write method in this file.
- `src/app/api/record/route.ts`: exports `POST` and `OPTIONS` with
  `skipAuth: true`. It requires a valid `x-umami-cache`, checks bots with
  `isbot`, and enforces blocked IPs. Body limit `MAX_RECORD_REQUEST_BYTES` =
  1,000,000 and at most 200 events per request. It refuses with
  `recorder_disabled`, `replay_disabled` or `heatmap_disabled` according to
  the website flags. Heatmaps are stored as `getUrlPath` (path only). Replay
  `events` are stored **as submitted**.
- `prisma/schema.prisma`:
  - `website.recorder_enabled` is a Boolean with default false, and
    `website.replay_config` is a Json field.
  - `session_replay`: rrweb events as `Bytes`, `created_at` nullable, index
    `(website_id, created_at)`.
  - `session_replay_saved`: `created_at` nullable, keyed by `visit_id`.
  - `heatmap_event`: `url_path` VARCHAR(500), `created_at` not null.

Deployed state checked:

- `mctl_get_service_status(team=admins, service=umami)`: Argo CD app
  `admins-umami`, project `apps`, Healthy and Synced. Image tag
  `3.4.0@sha256:85909afc...`, host `stats.mctl.ai`, port 3000,
  `hasDatabase: true`.
- `$MCTL_GITOPS_ROOT/services/admins/umami/values.yaml`: byte-identical
  (`diff`) to the clone's file. The deployed config therefore has only the
  two anonymous paths, recorder settings are not in GitOps, and retention
  is 2 years.
- Not observed: the live `website.recorder_enabled` and `replay_config`
  values in the database. No read-only tool reaches them. They are assumed
  to be default (false/NULL), because the seed Job never writes them, but a
  dashboard click could have set them. See Open questions.
- Not observed: mctl-web's current CSP, consent banner and privacy page.
  They are in another repository and were not read.

## Proposed solution

The work is split into staged slices. Only G1 and G2 belong to this
repository. S1 to S3 belong to the owning repos and are listed so that the
gates line up. Every slice gets its own PR and review.

### G1 (mctl-gitops): inert edge and retention. Safe to merge before any GO.

All of G1 is in `platform-gitops/services/admins/umami/values.yaml`.

1. **Three new exact routers** in `extraIngresses`, all on host
   `stats.mctl.ai` only, `pathType: Exact`, priority `"1000"`, and reusing
   `umami-tls`:
   - `admins-umami-recorder-script`: `/recorder.js`.
   - `admins-umami-recorder-config-mctl-ai`:
     `/api/websites/3735c207-d9bb-4968-8394-7a51c13a58d2/recorder`. One
     router per allowlisted website ID: this is the website-ID allowlist. A
     longer exact path at priority 1000 beats the main router's `/` prefix
     with forward-auth. Every other `/api/websites/...` path keeps falling
     through to forward-auth.
   - `admins-umami-record`: `/api/record`.

   A comment block records why each path exists and points at the upstream
   file it was verified against. It also states that the admins-umami.mctl.ai
   host gets none of these routes.
2. **Middlewares** in `extraObjects` (`traefik.io/v1alpha1`), attached with
   `traefik.ingress.kubernetes.io/router.middlewares` on the new routers
   only. The existing two routers are unchanged.
   - `admins-umami-record-body`: `buffering.maxRequestBodyBytes: 1000000`,
     equal to upstream `MAX_RECORD_REQUEST_BYTES`. It rejects oversize
     bodies before Umami reads them.
   - `admins-umami-recorder-ratelimit`: `rateLimit` with
     `sourceCriterion.requestHeaderName: CF-Connecting-IP`. Suggested values
     are `average: 5`, `period: 1s`, `burst: 30`. A recorder flushes at 20
     events or every 5 s, plus one rrweb checkout every 30 s, so a real
     visitor stays well below this. The final numbers come from staging
     measurement (T6).
   - `admins-umami-recorder-cors`: a `headers` middleware with
     `accessControlAllowOriginList: ["https://mctl.ai"]`,
     `accessControlAllowMethods: [GET, POST, OPTIONS]`,
     `accessControlAllowHeaders: [content-type, x-umami-cache]`,
     `accessControlMaxAge: 600`. It is attached only if the verification of
     `@/lib/cors` (task 1) shows that upstream answers with a wildcard or
     reflects the origin. Otherwise it is left out, so that two layers do
     not set conflicting CORS headers.
   - Method restriction is not added at the edge, because upstream exports
     only GET/OPTIONS on the config route and POST/OPTIONS on the record
     route (Next.js answers 405 for anything else). T2 asserts this.
3. **Declarative recorder settings, all off.** Extend the
   `admins-umami-seed-websites` SQL so that the `VALUES` list carries
   `recorder_enabled` and `replay_config` per website, and
   `ON CONFLICT ... DO UPDATE` also sets
   `recorder_enabled = EXCLUDED.recorder_enabled` and
   `replay_config = EXCLUDED.replay_config`. In G1 every website gets
   `false` and `NULL`. This makes GitOps the single source of truth: a
   dashboard toggle is reverted on the next sync, so nothing can be
   "silently activated".
4. **30-day retention for recorder data** in `admins-umami-retention`:
   - Change the `session_replay` and `heatmap_event` DELETEs to
     `interval '30 days'`.
   - Add `DELETE FROM session_replay_saved WHERE created_at IS NULL OR
     created_at < now() - interval '30 days'`. Saved replays fall under the
     30-day limit, because the issue says so explicitly. Once its
     `session_replay` chunks are gone, a saved replay plays nothing anyway.
   - Split the `$check$` loop: the general tables keep 2 years, and
     `session_replay`, `session_replay_saved` and `heatmap_event` are checked
     against 30 days.
   - Correct the comment that calls saved replays configuration.
   - The existing alerts then cover the new limit unchanged. Add a line to
     the alert annotation text naming the 30-day recorder limit.
5. **Runbook** `docs/runbooks/umami-recorder-pilot.md`, linked from
   `CLAUDE.md`'s secrets/runbooks list. It covers the routes and why they
   exist; how activation works (a G2 PR only); the kill switch, which is to
   revert G2, or as an emergency
   `UPDATE website SET recorder_enabled=false` followed by a sync, which
   re-asserts it; the pilot purge SQL for the pilot website IDs over
   `session_replay`, `session_replay_saved` and `heatmap_event`, with a
   zero-count check; and the verification commands.

G1 changes nothing for visitors. The config route answers `{enabled:false}`
and `/api/record` answers `recorder_disabled`, so even a page that loaded
`recorder.js` would record nothing.

### S1 to S3 (owning repos, separate proposals). Not written by this run.

- **S1 mctl-web (mctl.ai home):** a consent control for optional
  analytics. The default is off; withdrawal is persistent and acts
  immediately. The privacy-notice text is reviewed separately. A loader
  injects
  `<script defer src="https://stats.mctl.ai/recorder.js" data-website-id="3735c207-..." data-host-url="https://stats.mctl.ai">`
  only when all of the following hold:
  - consent is granted;
  - the host is exactly `mctl.ai`;
  - `location.pathname` is on an exact positive list (initially `/`);
  - `location.search === ''` and `location.hash === ''`;
  - `window.umami.getSession` exists.

  It also installs a first-party guard **before** the recorder loads. The
  guard wraps `fetch`, and `sendBeacon` if task 1 shows the recorder uses it,
  for requests to exactly `https://stats.mctl.ai/api/record`. It (a) drops
  every request once consent is withdrawn or the URL leaves the allowlist,
  and (b) removes query and fragment from heatmap `url`, from rrweb Meta
  `data.href`, and from `url-change` payloads, failing closed (drop) if a
  body does not parse. If the guard cannot be installed, the recorder is not
  loaded. In-page anchor links on pilot pages must not change `location.hash`
  (use `scrollIntoView`), and every link to a non-allowlisted route must be a
  full document navigation. Further changes: the CSP adds
  `https://stats.mctl.ai` to `script-src` and `connect-src`;
  `frame-ancestors 'self' https://stats.mctl.ai` is set only on the pilot
  pages, so X-Frame-Options is not removed globally (otherwise the blank
  heatmap overlay is accepted); and `Referrer-Policy: strict-origin` is set
  on pilot pages. Payloads are also given `[data-umami-private]` markers.
- **S2 mctl-telegram (tg.mctl.ai landing):** the same loader and guard,
  only after the mctl.ai pilot is accepted. GitOps then gets a matching G1'
  PR that adds the tg config router and settings.
- **S3 alice/docs, then Academy public catalog:** later. Academy also needs
  a privacy assessment first.

### G2 (mctl-gitops): activation PR for mctl.ai. Only after the gates and an explicit GO.

A one-website change to the seed SQL: `recorder_enabled=true` and
`replay_config =
{"heatmapEnabled":true,"heatmapSampleRate":1,"replayEnabled":<true|false per
GO>,"sampleRate":0.15,"maskLevel":"strict","maxDuration":300000,"blockSelector":"form, input, textarea, select, iframe, [contenteditable], [data-umami-private]"}`.
The key names must be verified in task 1. The PR body links the evidence of
T1 to T9, the independent review, and the owner GO. If replay cannot be
proven clean, G2 ships with `replayEnabled:false` (heatmaps only, which are
stored path-only on the server).

## Alternatives

- **Rely on Umami's per-site toggles in the dashboard, with no GitOps
  settings.** Dropped. Activation would be an unreviewed click, and
  rollback would have no audit trail. The issue forbids silent activation
  and bypassing release policy.
- **Open `/api/websites/*/recorder` with a prefix or regex router.**
  Dropped. `/api/websites` is the authenticated dashboard API, and a
  pattern risks exposing sibling routes. Exact one-path-per-ID routers make
  the website-ID allowlist visible in review.
- **Vendor a patched recorder in mctl-web (strip URLs, add stop() and
  consent in the recorder itself) instead of a fetch guard.** This is a
  stronger guarantee, but it forks upstream rrweb/Umami code that must
  then be tracked on every Umami bump, and it moves `recorder.js` off the
  pinned digest. It is kept as the fallback if task 1 shows the recorder
  bypasses `window.fetch`. If neither is possible, replay is not enabled.
- **Sanitize payloads at the edge.** Dropped. Traefik cannot rewrite JSON
  bodies without a custom plugin, which would put new code on the analytics
  path for the whole platform.
- **Keep 2-year retention for recorder data.** Dropped. The issue requires
  at most 30 days, including saved replays.

## Platform impact

- **Migrations:** none. The tables and columns already exist in 3.4.0, and
  `prisma migrate deploy` has run. The seed SQL change is idempotent.
- **Backward compatibility:** `/insights.js` and `/api/send` are untouched,
  and no middleware is added to them, so the essential tracker cannot
  regress. Forward-auth is unchanged for every other path. The mctl-portal
  forward-auth hosts list is unchanged.
- **Retention change:** on its first run after G1, the CronJob deletes any
  existing replay, saved-replay or heatmap rows older than 30 days. There
  should be none, because the recorder was never reachable, but the change
  is intended either way.
- **Resources:** replay chunks are up to 1 MB each. The `umami` pod is 50m
  CPU and 384Mi requested, 500m and 512Mi limit, and it already uses about
  305Mi at steady state. JSON parsing of 1 MB bodies can spike memory. Gate
  T6 measures CPU, memory, p95 latency of `/api/send` and DB growth per
  replay session on staging before G2. If memory headroom is short, G2 also
  raises the memory limit, as a separate reviewed change. Heatmaps at 100%
  are small: 20 events per batch.
- **Risks and mitigations:**
  - URL or PII leakage in replay: the S1 guard, strict masking, the block
    selector, the red-team gate, and replay off if it is not proven.
  - Dashboard exposure: exact routers only, and T2 asserts 401/302 on
    neighbouring paths.
  - Abuse and DB flooding: per-IP rate limit, edge body cap, upstream
    200-event cap, `x-umami-cache` requirement, and the bot check.
  - Activation drift: the seed Job re-asserts the settings on each sync.
  - Retention failure: the existing alerts.
  - Public config cache (`max-age=60`): after a kill switch, recording can
    continue for about 60 s to 6 min (`stale-while-revalidate=300`) in open
    tabs. That bound is documented. The immediate stop is the
    `recorder_enabled=false` check in `/api/record`, which is
    server-side and immediate.
