# Design: issue-126-feat-work-context-add-a-first-class-work

> **Superseded in part by the owner decisions of 2026-10-03 (see the top of tasks.md).** The
> WorkItem contract is mctl-api#349 (implemented) and on-behalf-of identity is mctl-api#350
> (implemented): the plugin uses the `surface:portal` principal with `X-MCTL-Surface-Actor` and a
> verified SurfaceIdentityLink, never the shared admin-bypass token; mctl-api is the authorization
> authority and portal checks are defense in depth only; there is no generic
> `/work-items/:id/actions/:actionId` API, only existing relay routes; `workItems.actionsEnabled`
> stays false by default. Statements below about mctl-api#227 being unavailable, the shared
> `MCTL_API_TOKEN`, `owner.team`/`authorizeForTeam` as the authorization path, `requiredRole` and
> `nextActions` are stale and are overridden by tasks.md.

## Current state
- The portal has no WorkItem, execution or ContextSnapshot concept, and Execution Canvas
  (mctlhq/mctl-portal#111) is not in the tree. A grep for `ExecutionCanvas` and `execution canvas`
  across `packages/` and `plugins/` finds nothing.
- Frontend routes live in one `FlatRoutes` tree in `packages/app/src/App.tsx`. The closest existing
  feature is mounted as `<Route path="/proposals/*" element={<ProposalsRoutes />} />`. The sidebar
  entry is in `packages/app/src/components/Root/Root.tsx`
  (`<SidebarItem icon={AssignmentIcon} to="proposals" text="Proposals" />`).
- The proposals feature sets the frontend pattern this proposal reuses:
  - `packages/app/src/components/proposals/ProposalsRoutes.tsx`: nested `Routes` with
    `:service/:slug` deep links.
  - `packages/app/src/components/proposals/api.ts`: a `ProposalsApi` class built on `DiscoveryApi`
    and `FetchApi`, with a `readJsonOrThrow` helper.
  - `packages/app/src/components/proposals/ProposalDetailPage.tsx`: Backstage `Page`, `Header`,
    `Content` and `ResponseErrorPanel`, MUI v4 `Grid`/`Paper`/`Chip`, `react-use` `useAsync` and
    `useAsyncFn`, and `useIsAdmin` from `packages/app/src/hooks/useIsAdmin.ts` (which checks
    `group:default/admins-owners`).
- `plugins/custom-domains-backend` sets the backend pattern for "thin gateway to mctl-api":
  - `src/mctlApiClient.ts`: `MctlApiDomainsClient` uses native `fetch` with
    `AbortSignal.timeout(10_000)`. It defines a typed `MctlApiError` that keeps upstream 4xx, maps
    401/403 and 5xx to 502, and keeps 5xx bodies and the token out of browser-facing messages. A
    defensive mapper, `toPortalDomain(raw: unknown)`, builds the portal shape. Empty or non-object
    bodies are rejected instead of being defaulted into a fake success.
  - `src/router.ts`: `express-promise-router`, `resolveCallerId` (user credential, then
    `user:default/<login>`), `authorizeForTeam` (admin bypass via `isAdminUser`, then
    `getTenantMember` from `plugins/tenant-backend/src/membershipLookup.ts`), and
    `respondToDomainsError`. It also contains the explicit warning that the plugin's bearer token is a
    platform-wide service credential that passes mctl-api's admin bypass, so the portal must do its own
    per-request ownership checks.
  - `src/plugin.ts`: `createBackendPlugin` with `coreServices.{logger,httpRouter,database,httpAuth,
    userInfo,rootConfig}`, config `customDomains.baseUrl`/`token`, and `registerAuthPolicies`
    (only `/health` is unauthenticated).
- Backend plugins are registered in `packages/backend/src/index.ts`
  (`backend.add(import('@internal/plugin-...'))`). Config lives in `app-config.yaml` and
  `app-config.production.yaml`. Production mctl-api is reached via `${MCTL_API_URL}` and
  `${MCTL_API_TOKEN}`.
- `plugins/proposals-backend/src/router.ts` (`resolveAdmin`) shows the rule this design keeps for
  writes: service principals are read-only, and write authority comes only from a user credential.

## Proposed solution

### 1. New backend plugin `plugins/work-items-backend` (gateway only)
This is a Backstage backend plugin (`pluginId: 'work-items'`) shaped like `custom-domains-backend`.
It owns no tables and does no cross-system joins.

- `src/types.ts`: the portal-side read shape. Every section carries an explicit observability marker
  so that "unknown" can never collapse into "empty":
  ```ts
  type Observed<T> =
    | { state: 'ok'; value: T; observedAt?: string }
    | { state: 'stale'; value: T; observedAt: string }
    | { state: 'unknown' | 'unobservable'; reason?: string };

  interface WorkItem {
    id: string; title: string;
    status: 'WAITING' | 'RUNNING' | 'BLOCKED' | 'COMPLETED' | string; // unrecognised values kept raw
    owner: { team: string; actor?: string };
    policySummary?: string;
    createdAt?: string; updatedAt?: string;
    surfaces: Observed<SurfaceRef[]>;       // kind, refId, transition, actor, at (no content)
    executions: Observed<ExecutionRef[]>;   // id, surface, status, startedAt, endedAt, current: boolean,
                                            // contextSnapshot: Observed<{id, version, provenance, status}>,
                                            // canvasRef?: string, resultSummary?, blocker?
    pending: Observed<PendingItem[]>;       // kind: 'human-input' | 'approval' | 'retry' | 'resume', ...
    blockers: Observed<Blocker[]>;
    nextActions: Observed<GovernedAction[]>;// id, kind, label, requiredRole
    evidence: Observed<EvidenceRef[]>;      // kind: issue|pr|deployment|trace|other, label, url
  }
  ```
- `src/mctlApiClient.ts`: `MctlApiWorkItemsClient` with `get(id)` and `act(id, actionId, actor,
  body)`. It reuses the custom-domains error policy (`MctlApiError`, 10 s timeout, 401/403/5xx mapped
  to 502, empty body treated as 502). The custom-domains code is copied, not imported across plugins,
  so that plugin stays untouched; extracting a shared module is a follow-up. `toPortalWorkItem(raw:
  unknown)` is the single mapping point:
  - A missing section maps to `{state:'unknown'}`, never to `[]`.
  - Upstream `stale`/`observedAt` markers pass through.
  - Only an allow-listed set of surface fields is copied, so transcript or message bodies cannot reach
    the browser by accident.
  - Evidence URLs that are not `http(s)` are dropped and counted, and the section becomes `stale` with
    a reason.
  The upstream path (provisionally `GET /api/v1/work-items/{id}`) must be checked against
  mctl-api#227 before implementation.
- `src/router.ts`:
  - `GET /health` is unauthenticated.
  - `GET /work-items/:id`: validate `id` against `/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/`, then
    `resolveCallerId`, fetch, then `authorizeForTeam(owner.team)`. If authorization fails, return 403
    and send nothing from the payload. A 404 from upstream is passed through.
  - `POST /work-items/:id/actions/:actionId`:
    1. Return 403 if `workItems.actionsEnabled` is false.
    2. Require a user credential; service principals are refused, as in proposals-backend.
    3. Re-fetch the WorkItem now (no cache), require that `actionId` is in the current `nextActions`
       or `pending`, require team membership, and require `requiredRole === 'admin'` → `isAdminUser`.
    4. Forward to mctl-api with the actor. mctl-api's policy is the final decision.
    5. Return the upstream result. The browser then re-fetches.
    The route never derives permission from surface history.
- `src/plugin.ts`: config keys `workItems.baseUrl` (default `https://api.mctl.ai`), `workItems.token`,
  `workItems.actionsEnabled` (default `false`) and `workItems.executionCanvasUrlTemplate` (optional,
  exposed to the frontend as `visibility: frontend` in a `config.d.ts`). Register it in
  `packages/backend/src/index.ts`. Add config blocks to `app-config.yaml` and
  `app-config.production.yaml` (reusing `${MCTL_API_URL}` and `${MCTL_API_TOKEN}`).

### 2. Frontend `packages/app/src/components/workItems/`
- `api.ts`: `WorkItemsApi` (same pattern as `ProposalsApi`) with `get(id)` and `act(id, actionId,
  body)`.
- `WorkItemsRoutes.tsx`: `/` is a minimal "open by ID" form, and `:workItemId` is
  `WorkItemDetailPage`. Mount it in `App.tsx` as `<Route path="/work-items/*" ...>`. A sidebar item is
  optional; put it behind a feature flag if added.
- `WorkItemDetailPage.tsx`, top to bottom on desktop (`Grid`, 8/4 columns):
  1. Header: ID (copyable), title, status `Chip`, owner team and policy summary.
  2. **Pending** panel, emphasized: current blocker, human input, approvals and next governed
     actions. Action buttons render only when `actionsEnabled` is true and the action is present;
     otherwise the panel shows read-only text. Every click shows a confirm `Dialog`, then calls
     `useAsyncFn` → `api.act`, then re-fetches. Nothing is updated optimistically.
  3. **Executions**: the current execution card first, then historical executions in reverse
     chronological order. Each shows its ContextSnapshot ID, version, provenance and status. The
     canvas link is built from the template, or the card shows "canvas unavailable".
  4. **Surfaces**: a metadata table (kind, ref, transition, actor, time).
  5. **Evidence**: an external link list grouped by kind.
- `ObservedSection.tsx`: a small wrapper that renders `unknown`/`unobservable` as a warning
  "Unknown" chip with the reason, and `stale` as "Stale since <time>". It renders "None" only when
  `state==='ok'` and the list is empty. All sections go through it, which is how acceptance item 8
  is enforced in one place.
- Mobile: use the MUI `useMediaQuery(theme.breakpoints.down('sm'))` hook to collapse to a single
  timeline list.

### 3. Backend follow-ups (not built here)
File focused issues against mctl-api for any part of #227 that does not provide: per-section
observability markers, `current` on executions, `canvasRef`, `requiredRole` on actions, and an
on-behalf-of actor for actions. The portal does not work around missing fields. They render as
Unknown.

## Alternatives
1. **Join GitHub, Temporal, Argo, proposal files and context storage in a portal backend plugin.**
   Dropped: the issue forbids it explicitly. It would duplicate platform reconciliation logic that
   mctl-api owns, and it would drift from the canonical contract.
2. **Extend `proposals-backend` or Execution Canvas (#111) to carry WorkItems.** Dropped: proposals
   are GitOps files with their own status machine (`isAllowedTransition`). Canvas is centred on one
   execution, and the issue says not to merge the two resources. A separate plugin and route keeps
   both independent while deep-linking between them.
3. **Use Backstage `proxy-backend` to expose mctl-api straight to the browser.** Dropped: there would
   be no place for per-request team authorization, transcript field stripping or error mapping. A
   shared service token would be exposed through the proxy, which is the exact risk documented in
   `custom-domains-backend/src/router.ts`.
4. **Ship actions on the shared service token now.** Dropped: mctl-api would see the portal as admin
   and its policy would not be evaluated for the real user. The design keeps actions behind
   `actionsEnabled=false` until on-behalf-of identity exists.

## Platform impact
- **Migrations:** none. The plugin does not use the database except to read tenant membership through
  the existing `membershipLookup`.
- **Backward compatibility:** these are additive routes (`/api/work-items/*`, `/work-items/*`). No
  existing plugin changes.
- **Resource impact:** one mctl-api call per page view and two per action (re-fetch, then act). There
  is no caching, which favours correctness over load. This is negligible at current portal scale.
- **Risks and mitigations:**
  - Contract drift with mctl-api#227 → a single mapper with fixture tests, and unknown fields become
    Unknown.
  - Leaking private conversation content → an allow-list mapper plus a test that injects `content`
    and `messages` fields and asserts they are absent.
  - Authorization bypass via the shared token → portal-side team check after fetch, a 403 that
    returns no payload, actions disabled by default, and service principals refused on writes.
  - Unknown rendered as success → the `Observed<T>` type plus the `ObservedSection` component, with
    tests.
  - Execution Canvas not shipped → the config template is optional and the UI degrades.
  - Upstream dependencies not ready → the UI ships against fixtures. Acceptance items 1 to 4 are
    checked end-to-end only once mctl-api#227 and the resume pilot have landed.
