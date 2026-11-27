# Tasks: issue-3042-feat-analytics-p1-umami-heatmaps-and-ses

- [ ] 1. Verify the pinned v3.4.0 source at tag `v3.4.0`. Record file paths
  and line refs in the runbook. Check:
  - the CORS headers of `src/lib/cors`;
  - the `replay_config` key names read by
    `src/app/api/websites/[websiteId]/recorder/route.ts`;
  - whether `src/recorder/index.js` sends with `fetch` only or also with
    `sendBeacon`;
  - whether `insights.js` exposes `window.umami.getSession`;
  - whether the built image's `/recorder.js` still holds
    `__COLLECT_API_HOST__` (curl a local `docker run` of the pinned digest);
  - whether self-hosted Umami purges replays by itself.

  DoD: each open question in requirements.md that this covers is answered
  in the PR description.
- [ ] 2. (depends on 1) In
  `platform-gitops/services/admins/umami/values.yaml`, add `extraIngresses`
  `admins-umami-recorder-script` (`/recorder.js`),
  `admins-umami-recorder-config-mctl-ai`
  (`/api/websites/3735c207-d9bb-4968-8394-7a51c13a58d2/recorder`) and
  `admins-umami-record` (`/api/record`). Each is `pathType: Exact` on
  `stats.mctl.ai` only, with `router.priority: "1000"` and TLS
  `umami-tls`, plus a comment citing the upstream source. DoD: `helm
  template` renders exactly five extra Ingresses, and only the three new
  ones carry `router.middlewares`.
- [ ] 3. (depends on 1) Add Traefik `Middleware` objects to `extraObjects`
  and reference them from the new routers: `admins-umami-record-body`
  (`buffering.maxRequestBodyBytes: 1000000`) and
  `admins-umami-recorder-ratelimit` (rateLimit on `CF-Connecting-IP`).
  Add `admins-umami-recorder-cors` only if task 1 shows the upstream CORS is
  wildcard or reflected. DoD: the rendered middleware names match the
  annotations
  (`admins-<name>@kubernetescrd`), and `validate-manifests.yml` passes.
- [ ] 4. Extend the `admins-umami-seed-websites` SQL with explicit
  `recorder_enabled` (false for all) and `replay_config` (NULL for all), and
  update both on conflict. DoD: on staging, a toggle set in the dashboard
  is reverted after a re-sync.
- [ ] 5. Change `admins-umami-retention`:
  - 30 days for `session_replay` and `heatmap_event`;
  - a new DELETE for `session_replay_saved` (NULL `created_at` included);
  - a split `$check$` (2 years for the general tables, 30 days for the
    three recorder tables);
  - a corrected comment;
  - an alert annotation mention in
    `platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml`.

  DoD: a staging run against seeded 31-day-old rows deletes them and
  succeeds, and a planted surviving row fails the Job.
- [ ] 6. Write `docs/runbooks/umami-recorder-pilot.md` (routes, activation
  via G2 only, kill switch, cache bound, purge SQL with zero-count check,
  verification) and link it from `CLAUDE.md`. DoD: the runbook is reviewed
  in the same PR as tasks 2 to 5. That PR is G1, merged inert.
- [ ] 7. (depends on 6; other repos, not this one) File the separate
  proposals: S1 for mctl-web (consent, allowlist loader, fetch guard, CSP,
  pilot-page `frame-ancestors`, Referrer-Policy, privacy notice) and later
  S2 for mctl-telegram. DoD: issues are linked from #3042 with these
  requirements quoted.
- [ ] 8. (depends on 2-6 and S1 on staging) Run gates T1 to T9 on a
  synthetic staging setup: a preview of `admins/umami` with a fake website
  ID and an S1 preview build. DoD: an evidence bundle is attached to #3042.
- [ ] 9. (depends on 8, an independent security and privacy review, and an
  explicit owner GO) G2 activation PR: set mctl.ai to `recorder_enabled=true`
  with the `replay_config` from design.md. Use `replayEnabled:false` if T4
  or T5 cannot prove clean payloads. DoD: the PR links the evidence and
  approvals, and production deploy is separately authorized.
- [ ] 10. (depends on 9) Read-only production verification: the route
  matrix (T2), the config response, the first heatmap and replay visible to
  an admin only, and resource levels. DoD: a staged success or blocker
  report is posted on #3042.
- [ ] 11. (depends on mctl.ai pilot acceptance) A G1'/G2' pair for
  tg.mctl.ai (`d4fa9d69-8b07-4d27-98e6-0b611eeaa707`). DoD: same as 2, 4, 8
  and 9 for that ID.

## Tests

- [ ] T1. Render check: `helm lint` and
  `helm template test platform-gitops/helm-charts/base-service -f
  platform-gitops/services/admins/umami/values.yaml`. Assert three new
  Exact ingresses on `stats.mctl.ai` only, the middlewares exist, the
  existing tracker and collect ingresses are byte-identical, and the main
  ingress still has forward-auth.
- [ ] T2. Route matrix on staging (curl, no cookie):
  - expect 200: `/recorder.js` and the allowlisted `/api/websites/<id>/recorder`;
  - expect 4xx from Umami, not forward-auth: `POST /api/record`;
  - expect a forward-auth redirect or 401:
    `/api/websites/<other-id>/recorder`, `/api/websites/<id>`,
    `/api/websites/<id>/recorder/x`, `/recorder.js/x`, `/api/record/x`,
    `/api/websites`, `/api/share/*` and `/`;
  - expect 405: `PUT`/`DELETE` on the new paths;
  - `admins-umami.mctl.ai` gets none of the new anonymous paths.
- [ ] T3. Limits: a 1,000,001-byte POST to `/api/record` is rejected at the
  edge. A burst above the limit from one `CF-Connecting-IP` gets 429. A
  preflight from `https://evil.example` is not allowed for that origin.
- [ ] T4. Capture red-team (S1 staging build), recording the raw
  `/api/record` bodies through a proxy and querying `session_replay.events`
  and `heatmap_event.url_path`. Plant the following:
  - fake tokens in the query and fragment;
  - fake phone numbers and emails in text;
  - form input;
  - hidden DOM nodes;
  - `[data-umami-private]` widgets;
  - links and SPA transitions to excluded routes.

  Assert: no `?` or `#` in any URL field or rrweb Meta `href`; no planted
  string in any stored byte; text and inputs masked; blocked elements
  absent.
- [ ] T5. Consent: with no consent, the recorder is never requested (no
  network call to `/recorder.js` or `/api/record`). After opt-in, recording
  starts. After withdrawal, no further `/api/record` request is made in the
  same tab, and none after a reload. `/insights.js` events are identical in
  all three states.
- [ ] T6. Load and resources: replay at 15% and heatmaps at 100% on desktop
  and mobile profiles. Measure Umami pod CPU and memory, p95 of `/api/send`
  and `/api/record`, DB bytes per replay session, and page LCP/INP with and
  without the recorder.
- [ ] T7. Playback and heatmap evidence: an admin plays a synthetic replay,
  and click and scroll heatmaps render, with the overlay or the accepted
  blank canvas. A request without forward-auth cannot reach either view.
- [ ] T8. Retention and cleanup: seeded rows older than 30 days, including
  `session_replay_saved`, are deleted by the CronJob. The runbook purge
  removes all pilot rows, and the zero-count check passes.
- [ ] T9. Disable and rollback drill: reverting G2 makes the config
  endpoint return `{enabled:false}` and `/api/record` return
  `recorder_disabled`. Reverting G1 removes the routes (forward-auth on all
  paths again). The essential tracker is unaffected throughout.

## Rollback

- **Kill switch (seconds):** revert the G2 PR and sync. For an emergency
  before the sync, run `UPDATE website SET recorder_enabled=false` from the
  runbook; the next sync of the seed Job re-asserts false. `/api/record`
  refuses at once. Open tabs may keep fetching the cached config for up to
  about 6 minutes, but their posts are refused.
- **Remove the edge (minutes):** revert the G1 PR. The three routers and
  their middlewares disappear, and every recorder path falls back to
  forward-auth. Retention can stay at 30 days. Reverting it only lengthens
  the window for tables that are empty by then.
- **Purge pilot data:** run the runbook purge SQL for the pilot website IDs
  over `session_replay`, `session_replay_saved` and `heatmap_event`, then
  the zero-count check. Record the purge on #3042.
- **Site side:** S1 and S2 are reverted in their own repos. Their loader
  fails closed, so a removed recorder route makes it inert.
