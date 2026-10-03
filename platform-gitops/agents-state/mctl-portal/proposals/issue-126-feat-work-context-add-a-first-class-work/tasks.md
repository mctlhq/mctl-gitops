# Tasks: issue-126-feat-work-context-add-a-first-class-work

> **Owner decisions, 2026-10-03 (approved with changes).** These tasks supersede design.md and
> requirements.md wherever they conflict:
> - The WorkItem runtime API (mctl-api#349) and delegated surface identity (mctl-api#350) are
>   implemented. Pin them; do not treat the contract or on-behalf-of identity as unavailable.
> - Canonical identity path: the `surface:portal` principal (`MCTL_SURFACE_PORTAL_TOKEN`) plus
>   `X-MCTL-Surface-Actor`, resolved by mctl-api through a verified SurfaceIdentityLink. The plugin is
>   NOT built on the shared admin-bypass `MCTL_API_TOKEN`.
> - mctl-api is the authorization authority. Portal-side checks are defense in depth only.
> - No invented `/actions/:actionId` API. UI actions map only to existing relay routes. An action
>   without a real endpoint renders read-only and gets a focused follow-up issue.
> - `workItems.actionsEnabled` stays `false` by default; this PR enables no mutation in production.

- [ ] 1. Pin the implemented contract into `plugins/work-items-backend/CONTRACT.md` (and a short
  doc comment at the top of `src/mctlApiClient.ts`): the mctl-api#349 WorkItem routes and response
  shapes, and the mctl-api#350 surface relay rules, taken from mctl-api `docs/work-context-contract.md`
  ("Surface relay (mctl-api#350)", "Execution requests (mctl-api#368)") and
  `internal/openapi/openapi.yaml`, naming the mctl-api revision. Record the relay allowlist exactly as
  it is: `GET /work-items/{id}`, `GET /work-items/{id}/intents[/{intent_id}]`,
  `GET|POST /work-items/{id}/execution-requests[/{request_id}]`, `POST /work-items/{id}/intents|surface-refs`,
  `GET /human-input[/{id}]`, `POST /human-input/{id}/response`, plus `POST /surface-identities/redeem`.
  Note that `GET /work-items/{id}/executions`, `/snapshots`, `/events` and `/evidence` are NOT relay
  routes today. Record the 403 codes (`link_not_found`, `link_revoked`, `link_expired`,
  `relay_required`) and what external id the portal sends as `X-MCTL-Surface-Actor` (the stable
  Backstage user identity, checked against #350's rules). Ownership/visibility is decided by
  mctl-api (WorkItem `tenant`); there is no `owner.team` field to invent. File focused mctl-api
  follow-up issues only for what is really missing (for example read-only relay access to
  executions/snapshots/evidence for surfaces). — DoD: CONTRACT.md exists, every field the mapper reads
  is in it, and follow-up issue links are in the PR description.
- [ ] 2. Scaffold `plugins/work-items-backend` (`package.json` named `@internal/plugin-work-items-backend`,
  `src/index.ts`, `src/plugin.ts`, `config.d.ts`), following `plugins/custom-domains-backend` for
  structure only: `/health` is the only unauthenticated route. Config keys: `workItems.baseUrl`,
  `workItems.surfaceToken` (the `surface:portal` token, secret), `workItems.actionsEnabled`
  (default false) and `workItems.executionCanvasUrlTemplate` (frontend visible). If `surfaceToken`
  is unset, every data route answers 503 `work_items_unconfigured`; the plugin never falls back to
  `MCTL_API_TOKEN` or any admin credential. (depends on 1) — DoD: `yarn tsc` and
  `backstage-cli package lint` pass; a test asserts no code path reads `MCTL_API_TOKEN`.
- [ ] 3. Implement `src/types.ts` (`Observed<T>`, `WorkItem` and its sub-types, only fields pinned in
  CONTRACT.md) and `src/mctlApiClient.ts` (`MctlApiWorkItemsClient`): every call carries
  `Authorization: Bearer <surfaceToken>` and `X-MCTL-Surface-Actor: <resolved user id>`, and calls only
  routes on the pinned relay allowlist. 10 s timeout; error mapping that preserves mctl-api's
  403/404/409 semantics (403 link_* → `link_required`, other 403 → `forbidden`, 404 kept, 5xx/timeout →
  502 with no upstream body or token in messages); an allow-list `toPortalWorkItem` where sections
  that are not observable through relay (executions, snapshots, evidence today) become
  `{state:'unknown', reason:'not_available_via_relay'}`, non-http(s) links are dropped, and there are
  no content or transcript fields. (depends on 2) — DoD: unit tests T1 to T4 pass.
- [ ] 4. Implement `src/router.ts` with `express-promise-router`:
  - `GET /work-items/:id`: ID regex, `resolveCallerId` (Backstage user credential only; service
    credentials → 401), then relay to mctl-api as that user. mctl-api's verdict is final: its 403/404
    pass through with no WorkItem payload. An optional portal-side check may only deny further
    (defense in depth); it can never grant what mctl-api refused.
  - `POST /surface-identities/redeem`: forwards `{code}` for the calling user, so a user can link the
    portal to their platform identity with a challenge code they created via GitHub login on
    mctl-api. Nothing else about linking happens in the portal.
  - Mutations: only routes on the pinned relay allowlist, and only those the UI uses (at most
    `POST /work-items/:id/execution-requests` for start/resume and
    `POST /human-input/:requestId/response`). Each returns 403 `actions_disabled` and makes no upstream
    call while `workItems.actionsEnabled` is false. No generic `/actions/:actionId` route exists.
  (depends on 3) — DoD: router tests T5 to T8 pass.
- [ ] 5. Register the plugin in `packages/backend/src/index.ts`. Add `workItems:` blocks to
  `app-config.yaml` (localhost:8080) and `app-config.production.yaml` (`${MCTL_API_URL}`,
  `${MCTL_SURFACE_PORTAL_TOKEN}`, `actionsEnabled: false`). Delivering that token to the portal
  deployment (Vault / mctl-gitops) is an owner-gated rollout step and is NOT part of this PR.
  (depends on 4) — DoD: the backend starts locally, `/api/work-items/health` returns 200, and data
  routes answer 503 while the token is unset.
- [ ] 6. Frontend `packages/app/src/components/workItems/`: `types.ts`, `api.ts` (`WorkItemsApi`, same
  pattern as `ProposalsApi`), `ObservedSection.tsx`, `WorkItemDetailPage.tsx` (header, Pending panel,
  execution requests, executions/ContextSnapshot sections rendered from pinned data or as "Not
  available yet" when not observable via relay, canvas link or "canvas unavailable", surfaces metadata,
  links, mobile single-column layout), a "Link your platform identity" state shown on `link_required`
  (enter a challenge code → redeem; no WorkItem data shown), `WorkItemsRoutes.tsx` (open-by-ID form plus
  `:workItemId`) and `index.tsx`. (depends on 4) — DoD: the page renders the T10 fixture.
- [ ] 7. Mount `<Route path="/work-items/*" element={<WorkItemsRoutes />} />` in
  `packages/app/src/App.tsx`. Optionally add a sidebar item in `components/Root/Root.tsx`. (depends on 6)
  — DoD: a deep link `/work-items/<id>` loads directly.
- [ ] 8. Action UI, only for the mutations wired in task 4: buttons render only when
  `actionsEnabled` is true AND the canonical state allows the action (for example the item is waiting
  for an execution request, or a human-input request is pending); confirm dialog; on success or
  failure re-fetch with no optimistic update; mctl-api errors (`state_version_conflict`,
  `execution_request_open`, ...) shown as returned. Every other "next step" the page shows is
  read-only text, with a follow-up issue filed for it. (depends on 6) — DoD: tests T11 and T12 pass.
- [ ] 9. Update `CLAUDE.md` and `plugins/README.md` plugin lists with `work-items-backend`, including
  the identity model (surface principal + relay, no admin token) and the flag. (depends on 2) — DoD:
  the docs list the new plugin.

## Tests
- [ ] T1. `toPortalWorkItem`: a fixture built from the pinned #349 response maps to the expected shape.
- [ ] T2. `toPortalWorkItem`: sections not observable through relay become
  `{state:'unknown', reason:'not_available_via_relay'}`, never `[]`. Upstream stale markers keep
  `observedAt`.
- [ ] T3. `toPortalWorkItem`: injected `content`, `messages` and `transcript` fields are absent from the
  output, and a `javascript:` link is dropped.
- [ ] T4. Client: every request carries the surface token and `X-MCTL-Surface-Actor`, and only
  allowlisted routes are callable (a request to `/executions` or `/resume` throws before any I/O);
  5xx → `MctlApiError(502)` with no body in the message; 403 link_* → `link_required`; 404 kept; empty
  200 body → 502; timeout → 502. The token never appears in thrown messages.
- [ ] T5. `GET /work-items/:id`: unauthenticated → 401; service credential → 401; invalid ID → 400;
  mctl-api 403/404 → passed through with no WorkItem fields; mctl-api 200 → 200; upstream down → 502;
  surface token unset → 503 and no upstream call. A portal admin gets no extra access: the request is
  still relayed as that user.
- [ ] T6. Each mutation route while `actionsEnabled=false` → 403 `actions_disabled`, and no upstream
  call is made. There is no `/actions/*` route (404).
- [ ] T7. Mutation with `actionsEnabled=true`: forwarded to the exact relay route with the caller as
  actor and the client's `expected_state_version`/idempotency key; mctl-api 4xx (409 conflict, 403)
  returned as-is; no `engine`, `engine_ref` or `execution_id` field is ever sent.
- [ ] T8. `POST /surface-identities/redeem` forwards `{code}` with the caller as actor; mctl-api errors
  pass through; the code never appears in logs.
- [ ] T9. `ObservedSection` renders "Unknown"/"Not available yet" for unknown or unobservable, "Stale
  since ..." for stale, and "None" only for an ok empty list.
- [ ] T10. `WorkItemDetailPage`: header, Pending panel, execution requests and the canvas link (or
  "canvas unavailable") render from the fixture; `link_required` renders the link form and no data.
- [ ] T11. Action buttons are hidden when `actionsEnabled` is false. With it true, clicking an allowed
  action calls the API and then re-fetches.
- [ ] T12. A rejected action shows the mctl-api error and re-fetches, and the local state is not
  changed optimistically.
- [ ] T13. Playwright e2e (`packages/app/e2e-tests/`): a deep link to a stubbed WorkItem renders the
  header and Pending panel on desktop, and a single column on a mobile viewport.

## Rollback
All changes are additive. To disable without a deploy of code: set `workItems.actionsEnabled: false`
(the default) to stop all mutations, and remove the sidebar item and route if needed. To roll back
fully, revert the PR. This removes `plugins/work-items-backend`, its `backend.add` line,
`packages/app/src/components/workItems/`, the `/work-items/*` route and the `workItems:` config
blocks. No database tables or migrations exist, so there is no data to restore. Upstream mctl-api is
not touched.
