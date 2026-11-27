# Umami Heatmaps and Session Replay: privacy-gated public landing pilot (GitOps slice)

## Context

Issue mctlhq/mctl-gitops#3042 (parent mctlhq/.github#349, narrowing #434)
asks to turn on Umami's heatmaps and session replay, using the existing
self-hosted Umami 3.4.0 (`platform-gitops/services/admins/umami/values.yaml`,
public host `stats.mctl.ai`). The pilot is narrow: first the public home page
of `mctl.ai` only, then the public `tg.mctl.ai` landing after the first site
is accepted, then allowlisted public pages of alice/docs, and Academy's
public catalog only after a separate privacy assessment. Today only the exact
paths `/insights.js` and `/api/send` reach Umami anonymously. Everything else,
including the dashboard and its API, sits behind Backstage forward-auth.

The pinned v3.4.0 source was inspected (see design.md). It shows three
properties that set the shape of this proposal:

1. The recorder needs three more anonymous routes: `GET /recorder.js`,
   `GET /api/websites/{websiteId}/recorder` (unauthenticated config, under
   the otherwise protected `/api/websites` tree) and `POST /api/record`.
2. `recorder.js` has no consent hook, no public stop API, no path or domain
   exclusion and no Do-Not-Track support.
3. The recorder strips no URL before sending. Heatmap events carry the full
   `location.href` (the server stores only the path, in `url_path`). Replay
   events are raw rrweb events, stored as sent. rrweb's Meta event carries
   `href`, and the recorder's `url-change` custom event carries the full URL.

So the privacy gates (consent, allowlist, stopping, URL sanitization) cannot
come from Umami or from GitOps. They must be built in the owning site repos.
This repository's job is a fail-closed edge: exact routes, an allowlist of
website IDs, rate and body limits, 30-day retention, and declarative per-site
toggles that start disabled. Every slice stays inert until the gates in the
issue have passed and an explicit GO has been given.

## User stories

- AS the platform owner I WANT the recorder's ingest routes exposed only for
  pilot website IDs and exact paths SO THAT enabling replay cannot widen
  public access to the Umami dashboard or API.
- AS the platform owner I WANT per-site recorder settings declared in GitOps
  and disabled by default SO THAT activation, sampling and masking are
  reviewed changes I can roll back with git, not dashboard clicks.
- AS a privacy reviewer I WANT replay and heatmap data, including saved
  replays, deleted after 30 days at most SO THAT retention matches the pilot
  promise and not the 2-year general analytics window.
- AS a visitor of mctl.ai I WANT nothing recorded unless I opt in, and
  recording to stop when I withdraw SO THAT optional analytics never runs
  without my consent and never affects the essential tracker or the service.
- AS an operator I WANT a documented disable, purge and rollback path SO
  THAT the pilot can be ended and its data removed in minutes.

## Acceptance criteria (EARS)

Edge routes (this repository):

- WHEN a request reaches `stats.mctl.ai` for exactly `/recorder.js`,
  exactly `/api/record`, or exactly
  `/api/websites/<pilot-website-id>/recorder` THE SYSTEM SHALL route it to
  Umami without forward-auth.
- IF a request targets any other `/api/websites/...` path, any other website
  ID's `/recorder` config path, a prefix or suffix of an allowlisted path, or
  any other Umami path THEN THE SYSTEM SHALL keep sending it through the
  existing Backstage forward-auth (`ingress.forwardAuth`).
- WHILE the pilot is in phase 1 THE SYSTEM SHALL allowlist only the mctl.ai
  website ID `3735c207-d9bb-4968-8394-7a51c13a58d2`. The tg.mctl.ai ID
  `d4fa9d69-8b07-4d27-98e6-0b611eeaa707` is added only in a separate,
  later PR.
- WHEN a request to `/api/record` has a body larger than 1,000,000 bytes THE
  SYSTEM SHALL reject it at the edge before Umami reads it. This matches
  upstream `MAX_RECORD_REQUEST_BYTES`.
- WHEN one client (`CF-Connecting-IP`) exceeds the configured request rate
  on `/api/record` or on the recorder config path THE SYSTEM SHALL answer 429.
- WHEN a browser sends a CORS preflight or request to `/api/record` or the
  config path from an origin outside the pilot allowlist THE SYSTEM SHALL NOT
  return an `Access-Control-Allow-Origin` that permits that origin.
- THE SYSTEM SHALL pin every new public router with
  `traefik.ingress.kubernetes.io/router.priority`, as the existing tracker and
  collect routers are pinned.

Per-site settings (this repository):

- THE SYSTEM SHALL declare `recorder_enabled` and `replay_config` for every
  seeded website in the `admins-umami-seed-websites` PostSync Job, so a
  dashboard change is reverted on the next sync.
- WHEN the routing slice merges THE SYSTEM SHALL keep `recorder_enabled =
  false` for every website. The recorder config endpoint then answers
  `{enabled:false}` and `/api/record` answers `recorder_disabled`.
- WHEN an approved activation PR sets the mctl.ai settings THE SYSTEM SHALL
  use `heatmapEnabled=true`, `heatmapSampleRate=1`, `replayEnabled` per the
  GO decision, `sampleRate=0.15`, `maskLevel=strict`, `maxDuration=300000`,
  and a `blockSelector` that covers forms, inputs, iframes and
  `[data-umami-private]`.
- IF the security or privacy review cannot prove that replay payloads carry
  no query string, fragment, token or identifier THEN THE SYSTEM SHALL keep
  `replayEnabled=false`, and the pilot SHALL continue with heatmaps only, or
  stop.

Retention and cleanup (this repository):

- THE SYSTEM SHALL delete rows of `session_replay`, `session_replay_saved`
  and `heatmap_event` older than 30 days on every daily run of
  `admins-umami-retention`.
- IF any row of those three tables is older than 30 days, or has a NULL
  `created_at`, after the DELETEs THEN THE SYSTEM SHALL fail the Job, so the
  existing `UmamiRetentionJobFailed` and `UmamiRetentionStale` alerts fire.
- WHEN the pilot is rolled back THE SYSTEM SHALL provide a documented, manual
  purge of all replay, saved-replay and heatmap rows for the pilot website
  IDs, and a check that none remain.

Site-side gates (owning repos, stated here as conditions this proposal
depends on; built and reviewed there):

- IF the visitor has not given affirmative optional opt-in THEN the site
  SHALL NOT load `recorder.js`.
- IF `location.pathname` is not on the exact positive allowlist, the host is
  not the pilot host, or `location.search` or `location.hash` is not empty
  THEN the site SHALL NOT load `recorder.js` (fail closed).
- WHILE the recorder runs, the site SHALL guarantee that no in-document
  navigation reaches an excluded route or a URL with a query or fragment.
  Either the page is a static document whose links all cause full
  navigation, or a first-party guard drops and sanitizes `/api/record`
  payloads and stops sending on navigation or withdrawal.
- WHEN the visitor withdraws consent the site SHALL stop sending recorder
  payloads at once, without a reload, and SHALL NOT load the recorder again
  until opt-in is given again.
- WHILE the recorder is loaded or blocked, the essential `/insights.js`
  tracker and the page SHALL behave exactly as before.

Release:

- THE SYSTEM SHALL NOT enable the recorder for any website in production
  until all of these exist: the synthetic staging evidence and the red-team
  evidence listed in tasks.md, an independent security and privacy review,
  and an explicit owner GO on the exact activation PR.

## Out of scope

- Code in mctl-web, mctl-telegram, mctl-alice, mctl-docs, mctl-academy: the
  consent UI, loader, allowlist guard, CSP and `frame-ancestors` headers,
  and privacy-notice text. These are proposed here as staged slices for
  their own repos and reviews. The investigator writes nothing to them.
- Phases 2 and 3 (alice/docs, Academy): each needs its own PR, and Academy
  also needs a separate privacy assessment.
- Any change to OAuth, forward-auth or the `mctl-portal` forward-auth hosts
  list, or exposing the dashboard or API publicly.
- Exposing replay data through MCP, Scout or any other tool, or sharing it
  externally. Umami share links stay behind forward-auth and are not used.
- Upgrading Umami past 3.4.0, or forking or patching the upstream recorder
  served by Umami.
- Changing the 2-year retention of general analytics tables.

## Open questions

- Which CORS headers does v3.4.0 `@/lib/cors` (`withCorsHeaders`,
  `getApiCorsHeaders`, `corsPreflight`) emit? It was not read. If it answers
  `*`, the proposal overrides it at the edge with a Traefik `headers`
  middleware allowlisting `https://mctl.ai`. That middleware must also allow
  the `x-umami-cache` request header. This must be verified.
- Does the recorder send with `window.fetch` (with `keepalive`) only, or
  also with `navigator.sendBeacon`? The first-party payload guard depends on
  the answer.
- Does `insights.js` 3.4.0 expose `window.umami.getSession()`, which the
  recorder needs to obtain `x-umami-cache`? Without it the recorder silently
  sends nothing.
- Does the `__COLLECT_API_HOST__` placeholder survive in the built image's
  `recorder.js`? If it does, sites must always set
  `data-host-url="https://stats.mctl.ai"`. This proposal assumes they do.
- What are the exact `replay_config` JSON key names that the config route
  reads (assumed: `replayEnabled`, `heatmapEnabled`, `sampleRate`,
  `heatmapSampleRate`, `maskLevel`, `maxDuration`, `blockSelector`)? Verify
  them against `src/app/api/websites/[websiteId]/recorder/route.ts` before
  the seed SQL is written.
- Does self-hosted 3.4.0 purge replays itself? The upstream docs say replays
  are "stored for 30 days", which may describe Umami Cloud only. This
  proposal enforces 30 days with its own CronJob either way.
- Which legal basis and consent mechanism do the existing mctl.ai privacy
  pages use, and does mctl-web already have a consent banner? The owner of
  that repo must answer. Until then the recorder stays disabled.
- Where is the synthetic staging environment? A preview of `admins/umami`
  with a fake website ID is assumed, because there is no non-production
  Umami. This needs to be confirmed.
