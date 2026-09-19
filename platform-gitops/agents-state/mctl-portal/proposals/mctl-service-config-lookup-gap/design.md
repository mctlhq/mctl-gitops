# Design: mctl-service-config-lookup-gap

## Current state
`mctl_get_service_config` was called for `admins/mctl-portal` for the first
time this cycle and returned "service not found: admins/mctl-portal". This
is distinct from, but possibly related to, the previously-tracked issue in
`proposals/argocd-service-field-gap/`, where `mctl_get_argocd_status` for
the same service succeeds (Healthy/Synced) but returns a null `service`
field. Both tools presumably read from some form of service-registration
metadata associated with the ArgoCD Application and/or a separate
config-registry store, but the exact data source for each tool call is not
established in `context/architecture.md` and needs investigation before a
fix is designed.

## Proposed solution
Two-phase approach:

**Phase 1 — Investigation (must complete before any fix work):**
1. Identify what backing store/API `mctl_get_service_config` reads from,
   and compare it against the backing store/API for the ArgoCD `service`
   field surfaced by `mctl_get_argocd_status`.
2. Determine whether both trace back to the same
   label/annotation/registration record (e.g. a `service` label on the
   ArgoCD Application, or a shared service-registry entry keyed by
   `tenant/service`), or whether `mctl_get_service_config` reads from an
   entirely separate config-registry index that was simply never populated
   for `mctl-portal`.
3. Document the finding explicitly (shared root cause vs. independent
   gap) as the deliverable of Phase 1, before Phase 2 begins.

**Phase 2 — Fix (branches on the Phase 1 finding):**
- **If shared root cause**: do not implement a fix here. Instead, add the
  `mctl_get_service_config` "not found" symptom as an additional
  acceptance criterion / expanded scope note on
  `proposals/argocd-service-field-gap/`, and mark this proposal as
  superseded/merged into that one, referencing it explicitly so it is not
  fixed twice.
- **If independent gap**: register `mctl-portal` (tenant `admins`) in
  whatever config-registry `mctl_get_service_config` reads from, populating
  at minimum service name, tenant, and current version fields, using the
  same values already known from `context/current-version.md` and the
  ArgoCD status. Add a regression check (e.g. a periodic or CI-time call to
  `mctl_get_service_config` for `admins/mctl-portal`) to catch future
  de-registration.

## Alternatives
- **Fix both symptoms independently without investigating shared root
  cause first**: rejected — risks duplicate work or two divergent fixes to
  what may be the same underlying label/registration gap, and was
  explicitly the mistake this proposal is designed to avoid per the
  analyst's rationale.
- **Defer until a third symptom appears to justify investigation cost**:
  rejected — this already risks breaking the researcher/analyst/spec-writer
  pipeline itself (which depends on `mctl_get_service_config`), so waiting
  for more evidence is not low-risk.
- **Wrap `mctl_get_service_config` calls in this agent pipeline with a
  fallback/retry instead of fixing the registry**: rejected — treats the
  symptom in the consumer rather than the root cause in the registry, and
  would mask rather than fix the underlying gap for other consumers of the
  tool.

## Platform impact
- **Migrations**: none expected in Phase 1 (investigation only). Phase 2's
  "independent gap" branch may require a small config-registry entry
  creation/update; no schema migration is anticipated, but this should be
  confirmed during investigation.
- **Backward compatibility**: no impact on other services' config lookups
  in either `admins` or `labs`; scoped to `admins/mctl-portal` only.
- **Resource impact**: negligible — a config-registry entry is metadata,
  not a workload change. No `labs`-tenant interaction at all.
- **Risks and mitigations**:
  - Risk: investigation concludes "shared root cause" but the merge into
    `argocd-service-field-gap` is not actually tracked, and the finding is
    lost. Mitigation: acceptance criteria require explicit documentation
    and cross-reference before this proposal is closed.
  - Risk: fixing the registry entry incorrectly (wrong tenant/service
    values) creates a new inconsistency. Mitigation: source values from
    `context/current-version.md` and the existing ArgoCD status output
    rather than inventing new values.
