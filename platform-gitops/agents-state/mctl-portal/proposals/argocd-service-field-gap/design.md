# Design: argocd-service-field-gap

## Current state
mctl-portal is deployed via nginx + Docker → mctl-gitops → ArgoCD into the `admins`
tenant (per `context/architecture.md`). ArgoCD status for mctl-portal currently
reports `health=Healthy`, `syncStatus=Synced`, `revision=2.6.3`, but the `service`
field in that status response has been `null` for at least two consecutive daily
cycles (2026-09-05, 2026-09-12). This is very likely a metadata/labeling gap in the
ArgoCD Application manifest (e.g., a missing or mis-set label/annotation that mctl's
tooling reads to populate `service`), rather than a deployment or health problem.

## Proposed solution
1. Inspect the ArgoCD Application manifest for mctl-portal in the mctl-gitops repo to
   identify which label/annotation/field mctl's status tooling expects to populate
   `service` (likely something like `app.kubernetes.io/name`,
   `mctl.ai/service`, or an ArgoCD Application `spec.info`/label entry, depending on
   how the platform's mctl tooling derives this field).
2. Compare mctl-portal's manifest against another `admins`-tenant service whose
   ArgoCD status correctly reports a non-null `service` field, to identify the
   missing piece.
3. Add or correct the missing label/annotation/field in mctl-portal's Application
   manifest in mctl-gitops.
4. Validate that this same fix does not need to be duplicated for the log-pipeline
   investigation (`portal-log-pipeline-gap`) — if both issues trace back to the same
   missing service label, fixing it here may also unblock or clarify that
   investigation's step 4 (Loki label matching).
5. Re-sync via ArgoCD and confirm the `service` field is populated on the next status
   query.

This is a manifest-metadata fix only — no application code, container image, or
runtime configuration changes are involved.

## Alternatives
- **Patch mctl's status tooling to tolerate/default a null `service` field** —
  rejected: this treats the symptom (tooling breaking on null) rather than the cause
  (missing metadata), and would need to be replicated for every future service with
  the same manifest gap.
- **Leave it as-is since there is no open incident yet** — rejected: the rationale
  explicitly flags this as a forward-looking risk for automation/dashboards that key
  off `service`; fixing it now is cheap (effort 1) versus fixing it reactively after
  tooling breaks.
- **Bundle this fix into the log-pipeline investigation as one combined proposal** —
  considered, but kept separate because this fix is independently cheap and
  low-risk (effort 1) and should not be blocked on the larger, higher-effort (effort
  3) log-pipeline investigation; the two proposals cross-reference each other instead.

## Platform impact
- **Migrations:** None. This is a manifest label/annotation addition, not a data or
  schema migration.
- **Backward compatibility:** No impact — adding a missing label/field is additive
  and does not change existing Application behavior, health checks, or sync policy.
- **Resource impact (especially `labs`):** None. This change is scoped to
  mctl-portal's Application manifest in `admins` only; `labs` is untouched.
- **Risks and mitigations:**
  - *Risk:* editing the Application manifest triggers an unwanted out-of-band sync
    or diff on unrelated fields.
    *Mitigation:* make the smallest possible diff (single label/annotation addition)
    and review the ArgoCD diff preview before merging in mctl-gitops.
  - *Risk:* the root cause turns out to be in mctl's status-reading tooling rather
    than the manifest itself.
    *Mitigation:* step 2 (comparison with a working service) should confirm which
    side the gap is on before any manifest change is made.
