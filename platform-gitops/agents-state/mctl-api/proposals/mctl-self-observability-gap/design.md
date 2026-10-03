# Design: mctl-self-observability-gap

## Current state
Per `context/architecture.md`, mctl-api hosts a 24-tool MCP server including `get_service_status`,
`get_service_config`, `get_service_logs`, and `get_tenant_metrics`. These tools integrate with:
- **ArgoCD** (`ARGOCD_TOKEN` from Vault) — application status (health/sync)
- **Backstage API** (`BACKSTAGE_TOKEN` from Vault) — service catalog
- **Kubernetes API** — pods/services/cronjobs/workflows status (presumably the source of
  pod-level CPU/memory/replica data)
- An unspecified log backend (Loki, per the inbox's speculation) for `get_service_logs`

Today, calling these tools with `team=admins, service=mctl-api` produces three distinct failure
modes, observed consistently across the 2026-08-22 and 2026-09-19 research cycles:
1. `get_service_config` → error `"service not found: admins/mctl-api"`.
2. `get_service_status` → succeeds for the ArgoCD-sourced fields (`health=Healthy`,
   `syncStatus=Synced`, `project=platform`, `updatedAt=...`) but returns a **null** `service` field
   where pod-level metrics would be.
3. `get_service_logs` → returns `count=0, lines=null` for a 24h window.

The fact that ArgoCD-sourced status data succeeds while catalog config, pod metrics, and logs all
fail suggests the bug is **not** in the ArgoCD integration, but in whatever service-catalog
resolution step (likely Backstage-catalog-key lookup) feeds the config/metrics/logs code paths.
This is consistent with a single root cause: mctl-api's own catalog entry (as scaffolded/registered
in Backstage) does not resolve under the exact key `admins/mctl-api` that these three tools query
by, even though the ArgoCD application `admins-mctl-api` does resolve under a similar-but-distinct
naming convention.

## Proposed solution
1. **Reproduce and isolate**: call all four tools (`get_service_status`, `get_service_config`,
   `get_service_logs`, `get_tenant_metrics`) against `team=admins, service=mctl-api` in a
   controlled environment, and against at least one other known-good `admins`-tenant service, to
   confirm the failure is specific to mctl-api's self-lookup and not a tenant-wide regression.
2. **Trace the catalog key**: inspect mctl-api's Backstage catalog registration (its own
   `catalog-info.yaml` or scaffolder-generated entry) and compare the exact `metadata.name` /
   `metadata.namespace` (or equivalent) against the string `admins/mctl-api` that
   `get_service_config` and `get_service_logs` construct internally when querying Backstage/Loki.
   The most likely root cause is a mismatch here (e.g. mctl-api registered as `mctl-api` under
   namespace `admins`, but looked up as a single combined string, or vice versa; or a
   `service.mctl.ai/component-id` label mismatch between the Kubernetes Deployment and the
   Backstage entity).
3. **Trace the metrics path**: inspect why `get_service_status`'s `service` field (pod-level
   CPU/memory/replica) is null for mctl-api specifically — likely the same catalog-key lookup used
   to find the Kubernetes Deployment/pods to query, since the ArgoCD-sourced top-level fields
   (which query by ArgoCD application name, a separate identifier) succeed.
4. **Trace the log path**: inspect the Loki (or equivalent) label selector `get_service_logs`
   constructs for `admins/mctl-api` and compare against the actual labels attached to mctl-api's
   own pods (e.g. `app.kubernetes.io/name`, `team`, `service`). Fix the selector or the pod label,
   whichever is the actual mismatch.
5. **Fix the identified mismatch(es)** at the resolution layer (preferred: fix the lookup/query
   code so it derives the correct key/selector the same way for every service, rather than special
   casing mctl-api) — this avoids a fragile "self special-case" fix and reduces the chance the same
   bug exists latently for other services not yet caught because no one has needed to introspect
   them the way this daily pipeline introspects mctl-api.
6. **Regression-test** by re-running all four tools against `team=admins, service=mctl-api` and
   confirming valid, non-null responses.

This is scoped as an investigation-plus-fix rather than a fully pre-specified code change, because
the exact root cause (catalog key mismatch vs. label mismatch vs. something else) is not yet known
— the inbox data confirms the symptom, not the cause. `tasks.md` reflects this by front-loading
investigation tasks before the fix task.

## Alternatives
1. **Hardcode a special-case lookup for `admins/mctl-api`** (e.g. an alias map). Rejected as the
   primary fix: papers over the real bug, and does not address the possibility that other services
   suffer the same class of failure but haven't been noticed yet (nothing else in the fleet gets
   introspected as frequently as mctl-api does by its own daily pipeline).
2. **Do nothing, rely on ArgoCD UI / Backstage UI directly for mctl-api's own status.** Rejected —
   defeats the purpose of having MCP tools at all for the service that hosts them, and continues to
   block the daily research pipeline's ability to self-diagnose ahead of the pgx/mcp-go upgrades.
3. **Rebuild `get_service_config`/`get_service_logs`/`get_tenant_metrics` from scratch with a new
   catalog-resolution abstraction.** Rejected as disproportionate — the ArgoCD-based status path
   already works correctly, indicating the overall architecture is sound and only a specific
   catalog-key or label lookup is broken.

## Platform impact
- **Migrations:** None expected. If the fix involves correcting a Backstage `catalog-info.yaml`
  entry or a Kubernetes label on mctl-api's own Deployment, that is a metadata/manifest change via
  mctl-gitops, not a data migration.
- **Backward compatibility:** No API-facing behavior change for any client other than the fixed
  return values becoming non-null/non-error for `admins/mctl-api` specifically. No other service's
  tool behavior should change (see the requirements' "document as follow-up" clause if the fix
  turns out to be broader).
- **Resource impact:** Negligible — this is a lookup/query correctness fix, not a new workload.
  No `labs` tenant impact — mctl-api runs only in `admins`, and this proposal does not touch the
  `labs` tenant's catalog entries.
- **Risks and mitigations:**
  - Risk: the root cause turns out to be a broader service-catalog defect affecting many services,
    expanding scope well beyond mctl-api. Mitigation: the investigation tasks explicitly check
    against a second known-good service first; if broader impact is found, it is documented as a
    follow-up finding (per the requirements' acceptance criterion) rather than silently expanding
    this proposal.
  - Risk: per `context/architecture.md`'s known limitation ("mctl-api itself authorizes tenant
    scope — a bug here = cross-tenant leak"), a catalog-key/lookup bug touching authorization logic
    could have security implications beyond observability. Mitigation: the investigation
    explicitly checks whether the same lookup path is used for authorization decisions; if so,
    treat as a security bug and escalate priority accordingly (flagged in `tasks.md` task 1).
  - Risk: fixing a Kubernetes pod label to match an expected selector could interact with other
    label-dependent systems (network policies, ArgoCD health checks). Mitigation: any label change
    is reviewed against existing NetworkPolicy/ServiceMonitor selectors before merge.
