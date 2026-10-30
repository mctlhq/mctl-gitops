# Tasks: issue-208-techdocs-first-view-after-every-portal-r

- [ ] 1. Confirm the `/sync/:namespace/:kind/:name` response contract of the installed `@backstage/plugin-techdocs-backend` 2.2.0 (JSON 200/304 vs `text/event-stream` only) by reading its `dist` router after `yarn install` — DoD: the chosen response handling is noted in a code comment in `techdocsWarmup.ts`.
- [ ] 2. Implement `runTechdocsWarmup(deps)` in `packages/backend/src/techdocsWarmup.ts`: list, filter on `backstage.io/techdocs-ref`, sequential build with per-entity try/catch, per-entity log line, summary line, returned counts (depends on nothing) — DoD: function exported, strict TypeScript compiles, no `let` where `const` suffices.
- [ ] 3. Implement `createSyncBuilder` (service token via `auth.getPluginRequestToken` with `getOwnServiceCredentials`, URL via `discovery.getBaseUrl('techdocs')`, per-entity timeout, 200/304/other mapping or event-stream handling per task 1) (depends on 1) — DoD: exported, non-success statuses throw with status in the message.
- [ ] 4. Implement `techdocsWarmupModule` (`createBackendModule({ pluginId: 'techdocs', moduleId: 'warmup' })`) reading `techdocs.warmup.*` and `techdocs.builder`, listing entities through `catalogServiceRef` with service credentials, and calling `scheduler.scheduleTask({ id: 'techdocs-warmup', scope: 'local', ... })` without awaiting builds (depends on 2, 3) — DoD: module registered in `packages/backend/src/index.ts` after the techdocs plugin; backend starts locally with `yarn start` and logs the warm-up summary after the initial delay.
- [ ] 5. Document `techdocs.warmup.*` keys (commented, with defaults) in `app-config.yaml` (depends on 4) — DoD: keys and defaults match the code.
- [ ] 6. Verify after deploy (depends on 4): restart the portal pod, without opening any docs page, wait ~5 minutes, check portal logs for one warm-up line per template entity and `ls` of the techdocs static `docs/` directory listing all 7 template sites; then open `/docs/default/template/onboard-service` in a fresh browser — DoD: page renders with no AbortError/404.

## Tests
- [ ] T1. `techdocsWarmup.test.ts`: `runTechdocsWarmup` with three annotated entities and one non-annotated entity calls `build` for exactly the three annotated refs, in order, and never for the non-annotated one.
- [ ] T2. Same suite: when `build` throws for the second entity, the third is still built, an error log containing the second entity's ref is emitted, and the returned counts report `failed: 1`.
- [ ] T3. Same suite: builds are sequential (a deferred-promise `build` mock asserts the next call does not start before the previous resolves).
- [ ] T4. Same suite: when `listEntities` rejects, an error is logged, `build` is never called and the function resolves (does not throw).
- [ ] T5. `createSyncBuilder`: 200 -> `updated`, 304 -> `cached`, 500 -> throws with status; request carries the service bearer token and the `/sync/<ns>/<kind>/<name>` path (mocked `fetch`, `discovery`, `auth`).
- [ ] T6. Module wiring: with `@backstage/backend-test-utils` `startTestBackend` and a mock scheduler, the module schedules `techdocs-warmup` with `scope: 'local'`; with `techdocs.warmup.enabled: false` it schedules nothing.
- [ ] T7. Prove red: temporarily remove the per-entity try/catch (or the annotation filter) and confirm T2 (or T1) fails; record this in the PR description.

## Rollback
Set `techdocs.warmup.enabled: false` in the portal's app-config (mctl-gitops values) and redeploy, which stops scheduling the task with no other effect. For a full rollback, revert the PR (the module file and its single `backend.add` line in `packages/backend/src/index.ts`); no data, schema or published docs need cleanup, since the publish directory is ephemeral.
