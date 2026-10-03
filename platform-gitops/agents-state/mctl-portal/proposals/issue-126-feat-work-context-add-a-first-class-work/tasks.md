# Tasks: issue-126-feat-work-context-add-a-first-class-work

- [ ] 1. Check the mctl-api#227 WorkItem contract (read path, action path, field names, observability
  markers, owner team). Record the verified mapping in a doc comment at the top of
  `plugins/work-items-backend/src/mctlApiClient.ts`, as `toPortalDomain` does. File focused mctl-api
  follow-up issues for missing fields (`current`, `canvasRef`, `requiredRole`, per-section staleness,
  on-behalf-of actor). — DoD: the mapping is written down, and follow-up issue links are listed in
  the PR description.
- [ ] 2. Scaffold `plugins/work-items-backend` (`package.json` named `@internal/plugin-work-items-backend`,
  `src/index.ts`, `src/plugin.ts`, `config.d.ts`). Follow `plugins/custom-domains-backend`: only
  `/health` is unauthenticated, and the config keys are `workItems.baseUrl`, `workItems.token`,
  `workItems.actionsEnabled` (default false) and `workItems.executionCanvasUrlTemplate` (frontend
  visible). (depends on 1) — DoD: `yarn tsc` and `backstage-cli package lint` pass.
- [ ] 3. Implement `src/types.ts` (`Observed<T>`, `WorkItem` and its sub-types) and `src/mctlApiClient.ts`
  (`MctlApiWorkItemsClient.get/act`, `MctlApiError`, 10 s timeout, error mapping, and an allow-list
  `toPortalWorkItem` where missing sections become `unknown`, non-http(s) evidence is dropped, and
  there are no content or transcript fields). (depends on 2) — DoD: unit tests T1 to T4 pass.
- [ ] 4. Implement `src/router.ts`: `GET /work-items/:id` (ID regex, `resolveCallerId`, then
  `authorizeForTeam` on `owner.team`, with no payload on 403) and
  `POST /work-items/:id/actions/:actionId` (flag gate, user credential only, fresh re-fetch, action
  must be currently offered, team and role check, then forward with actor, no caching). Use
  `express-promise-router`. (depends on 3) — DoD: router tests T5 to T8 pass.
- [ ] 5. Register the plugin in `packages/backend/src/index.ts`. Add `workItems:` blocks to
  `app-config.yaml` (localhost:8080) and `app-config.production.yaml` (`${MCTL_API_URL}`,
  `${MCTL_API_TOKEN}`, `actionsEnabled: false`). (depends on 4) — DoD: the backend starts locally and
  `/api/work-items/health` returns 200.
- [ ] 6. Frontend `packages/app/src/components/workItems/`: `types.ts`, `api.ts` (`WorkItemsApi`, same
  pattern as `ProposalsApi`), `ObservedSection.tsx`, `WorkItemDetailPage.tsx` (header, Pending panel,
  current then historical executions with ContextSnapshot metadata and canvas link or "canvas
  unavailable", surfaces metadata table, evidence links, mobile single-column layout),
  `WorkItemsRoutes.tsx` (open-by-ID form plus `:workItemId`) and `index.tsx`. (depends on 4) — DoD: the
  page renders a fixture with E1 and E2 and distinct C1 and C2.
- [ ] 7. Mount `<Route path="/work-items/*" element={<WorkItemsRoutes />} />` in
  `packages/app/src/App.tsx`. Optionally add a sidebar item in `components/Root/Root.tsx`. (depends on 6)
  — DoD: a deep link `/work-items/<id>` loads directly.
- [ ] 8. Governed action UI: buttons only when `actionsEnabled` is true and the action is offered, a
  confirm dialog, `useAsyncFn` → `api.act`, the error shown on rejection, and a re-fetch on both success
  and failure with no optimistic update. (depends on 6) — DoD: tests T11 and T12 pass.
- [ ] 9. Update `CLAUDE.md` and `plugins/README.md` plugin lists with `work-items-backend`.
  (depends on 2) — DoD: the docs list the new plugin.

## Tests
- [ ] T1. `toPortalWorkItem`: a full fixture (W1 with Telegram and MCP surfaces, E1/C1 historical, E2/C2
  current and blocked, pending approval, PR and trace evidence) maps to the expected shape.
- [ ] T2. `toPortalWorkItem`: missing `executions`, `pending` and `evidence` become `{state:'unknown'}`,
  never `[]`. Upstream stale markers keep `observedAt`.
- [ ] T3. `toPortalWorkItem`: injected `content`, `messages` and `transcript` fields on surfaces are
  absent from the output, and a `javascript:` evidence URL is dropped.
- [ ] T4. Client: 5xx → `MctlApiError(502)` with no body in the message; 401/403 → 502; 404 is kept;
  empty 200 body → 502; timeout → 502. The token never appears in thrown messages.
- [ ] T5. `GET /work-items/:id`: unauthenticated → 401; invalid ID → 400; non-member → 403 with no
  WorkItem fields in the body; member → 200; admin who is not a member → 200; upstream down → 502.
- [ ] T6. `POST .../actions/:actionId` while `actionsEnabled=false` → 403, and no upstream call is made.
- [ ] T7. `POST .../actions/:actionId` with a service credential → 401 or 403. With an action not in the
  freshly re-fetched `nextActions`/`pending` → 409, and nothing is forwarded. With
  `requiredRole: admin` and a non-admin member → 403.
- [ ] T8. `POST .../actions/:actionId`: an authorized member is forwarded with the actor. An upstream
  4xx rejection is returned as-is. The test asserts the WorkItem was re-fetched for this request,
  with no cache.
- [ ] T9. `ObservedSection` renders "Unknown" for unknown or unobservable, "Stale since ..." for stale,
  and "None" only for an ok empty list.
- [ ] T10. `WorkItemDetailPage`: the current execution comes before historical ones, C1 and C2 are
  shown with version and provenance, and the canvas link is present when the template is set and shows
  "canvas unavailable" when it is not. The Pending panel shows the blocker.
- [ ] T11. Action buttons are hidden when `actionsEnabled` is false. Clicking an action calls the API
  and then re-fetches.
- [ ] T12. A rejected action shows the error and re-fetches, and the local state is not changed
  optimistically.
- [ ] T13. Playwright e2e (`packages/app/e2e-tests/`): a deep link to a stubbed WorkItem renders the
  header, Pending panel and executions on desktop, and a single column on a mobile viewport.

## Rollback
All changes are additive. To disable without a deploy of code: set `workItems.actionsEnabled: false`
(the default) to stop all mutations, and remove the sidebar item and route if needed. To roll back
fully, revert the PR. This removes `plugins/work-items-backend`, its `backend.add` line,
`packages/app/src/components/workItems/`, the `/work-items/*` route and the `workItems:` config
blocks. No database tables or migrations exist, so there is no data to restore. Upstream mctl-api is
not touched.
