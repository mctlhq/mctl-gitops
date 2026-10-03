# Tasks: argocd-service-field-gap

- [ ] 1. Identify which label/annotation/field mctl's status tooling reads to
      populate the `service` field — DoD: documented mapping (field name/source)
      confirmed against mctl tooling or its docs.
- [ ] 2. Compare mctl-portal's ArgoCD Application manifest against another
      `admins`-tenant service with a correctly non-null `service` field (depends on
      1) — DoD: specific missing/incorrect label or field identified for
      mctl-portal.
- [ ] 3. Cross-check whether this same gap explains the `portal-log-pipeline-gap`
      symptom (depends on 2) — DoD: documented conclusion (shared root cause or
      unrelated), recorded in both proposals.
- [ ] 4. Add/correct the identified label/annotation in mctl-portal's Application
      manifest in mctl-gitops (depends on 2) — DoD: PR opened with a minimal, single
      -purpose diff.
- [ ] 5. Review the ArgoCD diff preview and merge (depends on 4) — DoD: manifest
      change merged, ArgoCD sync triggered with no unrelated field changes.
- [ ] 6. Confirm the `service` field is populated on the next ArgoCD status query
      (depends on 5) — DoD: `service` field returns `mctl-portal` (non-null),
      health/syncStatus unchanged (Healthy/Synced).

## Tests
- [ ] T1. Query ArgoCD status for mctl-portal post-merge and confirm `service` is
      non-null and correctly set.
- [ ] T2. Confirm no regression in `health`/`syncStatus`/`revision` fields for
      mctl-portal after the manifest change.
- [ ] T3. Spot-check one other `admins`-tenant Application manifest to confirm the
      fix pattern did not inadvertently get applied there.

## Rollback
Revert the single manifest label/annotation commit in mctl-gitops; ArgoCD will
re-sync to the prior manifest state. Since this is a metadata-only change, no
running workload, data, or session is affected by a rollback.
