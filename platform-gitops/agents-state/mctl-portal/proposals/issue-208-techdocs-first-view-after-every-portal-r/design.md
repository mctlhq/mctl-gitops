# Design: issue-208-techdocs-first-view-after-every-portal-r

## Current state
- `packages/backend/src/index.ts` registers `@backstage/plugin-techdocs-backend` (`backend.add(import('@backstage/plugin-techdocs-backend'))`) and `@backstage/plugin-search-backend-module-techdocs`. There is no code in the repo that builds docs proactively; builds happen only when the frontend reader calls `GET /api/techdocs/sync/:namespace/:kind/:name`.
- `app-config.yaml` (lines 66-71): `techdocs.builder: 'local'`, `generator.runIn: 'local'`, `publisher.type: 'local'`. `app-config.production.yaml` has no `techdocs` key, so the same local builder/publisher applies in production unless overridden by the gitops values (the issue reports `bootstrap/templates/mctl-platform/mctl-portal.yaml` sets the same).
- `packages/backend/package.json` pins `@backstage/plugin-techdocs-backend` `^2.2.0` (yarn.lock: 2.2.0, depending on `@backstage/plugin-techdocs-node` `^1.15.0`), `@backstage/backend-plugin-api` `^1.9.1`, `@backstage/plugin-catalog-node` `^2.2.1`.
- Local backend modules already exist in `packages/backend/src` with sibling Jest tests: `githubAuthModule.ts`/`.test.ts`, `zitadelAuthModule.ts`/`.test.ts`, `kubernetesEntityScope.ts`/`.test.ts`. `kubernetesEntityScope.ts` uses `createBackendModule` and `catalogServiceRef` from `@backstage/plugin-catalog-node`, a pattern this change follows.
- Scheduling precedent: `plugins/tenant-backend/src/plugin.ts` uses `coreServices.scheduler.scheduleTask({ id, frequency, timeout, initialDelay, fn })` for `workspace-ready-notifications`.
- Permissions: `plugins/permission-backend-module-team-policy/src/module.ts` `TeamBasedPermissionPolicy.handle` notes that `ServerPermissionClient` resolves service principals locally and never forwards them to the policy; so a request made with the backend's own service credentials can read every catalog entity and is not subject to the team policy's DENY for missing users.
- Deployed state checked:
  - `mctl_get_service_status(team=admins, service=mctl-portal)`: ArgoCD app `admins-mctl-portal`, Healthy, Synced, revision `2.6.3`, updated 2026-10-25T14:50:26Z; `service: null` (not a catalogue service, so no values.yaml through this tool).
  - `$MCTL_GITOPS_ROOT/services/` (admins, karabu, labs): no mctl-portal entry and no `techdocs` match; the portal's deployment is in mctl-gitops `bootstrap/`, which is not in this checkout. Replica count and production `techdocs` values were therefore not observed directly; I rely on the issue's verified statement for `builder: local`/`publisher: local`.
  - The installed techdocs-backend source (node_modules) was not present in the clone, so the sync route's response modes are described from the upstream 2.x behaviour and flagged as an open question.

## Proposed solution
Add a backend module `techdocsWarmupModule` in `packages/backend/src/techdocsWarmup.ts`, registered in `packages/backend/src/index.ts` right after the techdocs plugin (`backend.add(techdocsWarmupModule)`), with `pluginId: 'techdocs'`, `moduleId: 'warmup'`.

Split into a pure, testable loop and a thin module wrapper:

1. `runTechdocsWarmup(deps)` where deps are `{ listEntities: () => Promise<Entity[]>, build: (ref) => Promise<'updated' | 'cached'>, logger }`. It:
   - calls `listEntities()`; on failure logs an error and returns `{ ok: 0, failed: 0, listFailed: true }`;
   - filters defensively to entities whose `metadata.annotations['backstage.io/techdocs-ref']` is set (skip others even if the catalog filter returned them);
   - iterates with `for ... of` and `await` (sequential), each in its own try/catch; logs `info` `techdocs warm-up: <ref> updated|up to date` or `error` `techdocs warm-up: <ref> failed: <message>`;
   - logs a summary `techdocs warm-up finished: N built, M up to date, K failed` and returns the counts (so failures are reported, not swallowed).
2. `createSyncBuilder({ discovery, auth, fetch, timeoutMs })` returns `build(ref)`: obtains `auth.getPluginRequestToken({ onBehalfOf: await auth.getOwnServiceCredentials(), targetPluginId: 'techdocs' })`, calls `${await discovery.getBaseUrl('techdocs')}/sync/${namespace}/${kind}/${name}` with `Authorization: Bearer <token>`, and an `AbortSignal.timeout(timeoutMs)` (default 5 minutes, well above the observed 20 s). Status 200 -> `updated`, 304 -> `cached`, anything else -> throw with status and body excerpt. If the route only serves `text/event-stream`, read the stream to its `finish` event (success) or `error` event (throw). Going through the route reuses exactly the preparer/generator/publisher chain, the build-strategy checks and the in-process build locking (`DocsSynchronizer`) the browser path uses, so a warm-up and a concurrent visitor never run two builds of one entity.
3. Catalog listing: `catalog.getEntities({ filter: { 'metadata.annotations.backstage.io/techdocs-ref': CATALOG_FILTER_EXISTS }, fields: ['kind','metadata.namespace','metadata.name','metadata.annotations'] }, { credentials: await auth.getOwnServiceCredentials() })` via `catalogServiceRef`.
4. Module `init` deps: `coreServices.logger`, `coreServices.scheduler`, `coreServices.discovery`, `coreServices.auth`, `coreServices.rootConfig`, `catalogServiceRef`. In `init` it only calls `scheduler.scheduleTask({ id: 'techdocs-warmup', scope: 'local', frequency: { minutes }, initialDelay: { seconds }, timeout: { minutes: 60 }, fn })` (not awaited work), so readiness is not blocked. `scope: 'local'` is essential: the default `global` scope takes a DB lock and would build on only one replica, while every pod has its own ephemeral publish directory. The initial delay (default 60 s) lets the catalog finish its first ingestion; an empty first list is harmless and also covered by later runs.
5. Config (optional, all defaulted, read with `getOptional*`): `techdocs.warmup.enabled` (default true), `techdocs.warmup.initialDelaySeconds` (60), `techdocs.warmup.frequencyMinutes` (30), `techdocs.warmup.entityTimeoutSeconds` (300). If `techdocs.builder` is not `local`, the module logs that warm-up is skipped and schedules nothing (the external builder model has no local cache to warm). Document the keys in `app-config.yaml` as comments.

## Alternatives
- Persistent volume for the publish directory: rejected by the issue (billed Hetzner volume, diverges across replicas).
- Calling `DocsBuilder`/`Preparers`/`Generators`/`Publisher` from `@backstage/plugin-techdocs-node` directly inside the module: same result, but duplicates the techdocs-backend wiring (publisher instance, cache, build strategy) and bypasses its per-entity sync lock, so a warm-up and a browser request could build the same entity concurrently into the same directory. The authenticated internal `/sync` call is less code and identical to the user path.
- Raising the frontend sync timeout or retrying in the reader: still shows a slow first view and does not address scheduled rebuilds; requires frontend overrides of upstream components.
- Switching to an object-storage publisher (S3/GCS) with CI-built docs: correct long-term, but needs new infrastructure, credentials and a CI pipeline; out of scope.

## Platform impact
- No migrations. `catalogServiceRef` comes from `@backstage/plugin-catalog-node` (already a dependency). `CATALOG_FILTER_EXISTS` is exported by `@backstage/catalog-client`, which is not listed in `packages/backend/package.json`; add it as a direct dependency at the version already in yarn.lock.
- Resource impact: with 7 template entities at ~20 s each, a cold-start run takes ~2-3 minutes of mkdocs CPU per pod, sequential so at most one mkdocs process at a time from the warm-up. Scheduled runs are mostly cache hits (304) once nothing changed, but each still prepares (git/dir fetch) per entity; at 30 min frequency this is negligible.
- Risk: the warm-up competes with the first user requests for CPU in the first minutes after start. Mitigation: sequential builds and an initial delay.
- Risk: a failing docs source floods logs. Mitigation: one error line per entity per run (at most 48 runs/day).
- Risk: the service-to-service call is rejected (auth/permission). Mitigation: it surfaces as per-entity errors in logs; service principals bypass the team permission policy as noted above.
- Backward compatible: disabling via `techdocs.warmup.enabled: false` restores today's behaviour exactly.
