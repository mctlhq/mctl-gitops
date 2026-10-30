# Warm the TechDocs cache on portal startup and on a schedule

## Context
mctl-portal runs TechDocs with `builder: local` and `publisher: local` (`app-config.yaml` `techdocs:` block; production values come from mctl-gitops `bootstrap/templates/mctl-platform/mctl-portal.yaml`). Built sites are written to the techdocs-backend static directory on the pod's ephemeral filesystem, so every restart or deploy starts with no published docs. The first visitor to any TechDocs page triggers a ~20 s build; the browser's sync request aborts before it finishes (`AbortError`), the reader falls back to the missing `index.html`, and the user sees `ERROR 404: NotFoundError`. A reload later works because the backend finished the build anyway. An external tenant owner reported the docs as broken on 2026-10-25.

The issue asks for a backend module in `packages/backend/src` that, after startup and then periodically, builds the docs for every catalog entity carrying `backstage.io/techdocs-ref`, through the same path the `/sync` route uses, sequentially, isolating per-entity failures, logging each result, and never blocking backend readiness.

## User stories
- AS a tenant owner I WANT the first TechDocs page I open after a portal deploy to render SO THAT I do not conclude the docs are broken.
- AS a platform operator I WANT each warm-up result logged per entity SO THAT a broken docs source is visible in Loki without a user reporting it.
- AS a docs author I WANT docs changed in git to be rebuilt periodically SO THAT readers see the update without being the one who triggers the rebuild.

## Acceptance criteria (EARS)
- WHEN the portal backend has started THE SYSTEM SHALL, after an initial delay of about 1 minute (configurable), build the TechDocs site of every catalog entity carrying the `backstage.io/techdocs-ref` annotation, without any browser request.
- WHEN a warm-up run starts THE SYSTEM SHALL list entities from the catalog filtered on `metadata.annotations.backstage.io/techdocs-ref` and SHALL NOT build entities without that annotation.
- WHILE a warm-up run is in progress THE SYSTEM SHALL build entities one at a time (sequentially), each through the techdocs-backend `/sync/:namespace/:kind/:name` route called with the backend's own service credentials.
- WHEN an entity build finishes THE SYSTEM SHALL log one line per entity with its entity ref and outcome (`updated`, `up to date`, or `failed`), and one summary line per run with the counts.
- IF one entity's build throws, times out or returns a non-success status THEN THE SYSTEM SHALL log it at error level with the entity ref and cause, and SHALL continue with the remaining entities.
- IF listing the catalog fails THEN THE SYSTEM SHALL log an error and end the run, leaving the next scheduled run to retry.
- WHEN the backend starts THE SYSTEM SHALL register the warm-up without awaiting any build, so that backend readiness and plugin startup are never delayed by it.
- WHILE the portal runs THE SYSTEM SHALL repeat the warm-up on a schedule (default every 30 minutes, configurable) on every replica (scheduler scope `local`), because each pod's publish directory is its own.
- WHERE `techdocs.warmup.enabled` is `false` THE SYSTEM SHALL not schedule the warm-up; the default is enabled.
- WHEN a fresh pod has been running for a few minutes with no browser visit THE SYSTEM SHALL have a published site for every techdocs entity, so the first browser view renders without `AbortError` or 404.

## Out of scope
- A persistent volume or shared object storage (S3/GCS publisher) for the publish directory.
- Changing the TechDocs frontend reader, the sync timeout in the browser, or the techdocs-backend package itself.
- Fixing the docs sources under `platform-gitops/backstage/templates/*` (verified fine in the issue).
- Building docs for entities created between scheduled runs immediately on registration (they are built by the next run or by the first visit, as today).

## Open questions
- Exact production replica count of mctl-portal was not observed (the deployment lives in mctl-gitops `bootstrap/`, not in the `services/` checkout). The design uses scheduler scope `local` so it is correct for any replica count; with N replicas each pod builds every entity, which is intended.
- The issue's "4.29.0" and the ArgoCD revision `2.6.3` reported by `mctl_get_service_status` differ; presumably chart vs image versions. Not material to the design.
- Whether the techdocs `/sync` route's non-event-stream (JSON) response mode is still served by `@backstage/plugin-techdocs-backend` 2.2.0 must be confirmed by the implementer against the installed package (node_modules were not available in this clone). If it is not, the module consumes the `text/event-stream` response until its `finish`/`error` event instead.
