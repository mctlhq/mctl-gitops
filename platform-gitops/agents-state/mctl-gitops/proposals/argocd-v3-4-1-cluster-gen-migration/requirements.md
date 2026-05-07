# ArgoCD v3.4.1 Cluster-Generator Label Format Migration

## Context

The platform uses ArgoCD's App-of-Apps pattern with ApplicationSets backed by the cluster
generator (ADR-0001). The cluster generator matches Kubernetes cluster Secrets by label;
one of the labels in use is `argocd.argoproj.io/kubernetes-version`, which carries the
cluster's Kubernetes version and is consumed by ApplicationSet templates to parameterize
per-cluster deployments.

ArgoCD v3.4.1 — released May 7, 2026 — introduces a breaking change aligned with Helm
3.19.0: the `argocd.argoproj.io/kubernetes-version` label value must now follow the
`vMajor.Minor.Patch` format (e.g., `v1.30.0`). Labels that do not conform to this format
are rejected, and ApplicationSets using those labels will stop generating Applications.
Existing Applications already generated are not deleted, but no new generations or
re-generations will succeed until the labels are corrected. This creates a risk of silent
drift: operators may not immediately notice that ApplicationSets have stopped reconciling.

Both existing ArgoCD 3.4 upgrade proposals (`argocd-v3-4-upgrade-plan` and
`argocd-v3-4-upgrade-plan-v2`) targeted v3.4.0 and do not include this migration task.
Without a dedicated label-migration proposal, the platform risks upgrading to v3.4.1 before
the label format is corrected, leaving ApplicationSets broken.

## User stories

- AS a platform operator I WANT all cluster Secret labels migrated to the `vMajor.Minor.Patch`
  format before ArgoCD is upgraded to v3.4.1 SO THAT ApplicationSets continue generating
  Applications without interruption after the upgrade.
- AS a tenant team using ApplicationSets I WANT clear error messages in the ApplicationSet
  controller logs when a label format is invalid SO THAT I can identify and fix the issue
  quickly rather than debugging silent drift.

## Acceptance criteria (EARS)

- WHEN ArgoCD is upgraded to v3.4.1 THE SYSTEM SHALL continue generating Applications from
  all existing ApplicationSets without any gap or error caused by label format rejections.
- BEFORE the ArgoCD chart version is changed to v3.4.1 THE SYSTEM SHALL have all
  `argocd.argoproj.io/kubernetes-version` labels on cluster Secrets and in ApplicationSet
  specs updated to the `vMajor.Minor.Patch` format.
- WHEN a cluster Secret carries a `kubernetes-version` label that does not match
  `vMajor.Minor.Patch` after upgrade THE SYSTEM SHALL emit a clear, structured error in
  the ApplicationSet controller logs identifying the offending ApplicationSet and label
  value.
- IF the ArgoCD upgrade is performed before label migration is complete THEN existing
  Applications already generated SHALL remain in place and SHALL NOT be deleted, but new
  ApplicationSet generations SHALL fail until the labels are corrected.
- WHILE label migration is in progress THE SYSTEM SHALL continue reconciling all
  ApplicationSets that do not use `kubernetes-version` labels without disruption.

## Out of scope

- Migrating away from the ApplicationSet cluster generator to any other generator type
  (rejected by ADR-0001).
- Upgrading ArgoCD to v3.5.x or any version beyond v3.4.1.
- Changing the cluster generator to a directory generator or any other generator pattern.
- Modifications to ApplicationSet templates unrelated to the `kubernetes-version` label
  format change.
