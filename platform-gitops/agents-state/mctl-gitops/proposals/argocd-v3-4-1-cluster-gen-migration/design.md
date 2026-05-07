# Design: argocd-v3-4-1-cluster-gen-migration

## Current state

ArgoCD is at v3.4.0, as targeted by the existing `argocd-v3-4-upgrade-plan` and
`argocd-v3-4-upgrade-plan-v2` proposals. The platform's App-of-Apps pattern (mandated by
ADR-0001) uses ApplicationSets defined in `platform-gitops/apps/`. The cluster generator
within these ApplicationSets references Kubernetes cluster Secrets and matches on labels
including `argocd.argoproj.io/kubernetes-version`.

The `argocd.argoproj.io/kubernetes-version` label is currently set on cluster Secrets in
an unspecified format (e.g., `1.30`, `1.30.0`, or `v1.30`). ArgoCD v3.4.0 accepted
multiple formats; v3.4.1 enforces strict `vMajor.Minor.Patch` (e.g., `v1.30.0`) alignment
with Helm 3.19.0's version parsing. Any label value that does not match the strict format
will cause the cluster generator to skip that cluster entry, silently stopping Application
generation for that cluster.

The v3.4.1 release also delivers 150+ bug fixes and new ApplicationSet features (health
field, Watch API), making it the correct target version for the platform.

## Proposed solution

A two-step, sequenced migration:

**Step 1 — Label audit and correction (before any ArgoCD version change)**

Grep `platform-gitops/` for all occurrences of `argocd.argoproj.io/kubernetes-version` in:
- Kubernetes cluster Secrets (under `platform-gitops/bootstrap/` or wherever cluster
  Secrets are defined in the repo).
- ApplicationSet specs (under `platform-gitops/apps/`) where the label value is used as a
  literal or a template variable.

For each occurrence, normalize the value to `vMajor.Minor.Patch` (e.g., `v1.30.0`). Apply
the label changes via a PR. After merge, ArgoCD v3.4.0 reconciles the ApplicationSets with
the new labels immediately — no ArgoCD restart is needed, as label changes on cluster
Secrets trigger an ApplicationSet controller reconciliation.

**Step 2 — ArgoCD chart upgrade to v3.4.1**

Update the ArgoCD Helm chart version to v3.4.1 in `platform-gitops/services/admins/` first,
monitor the ApplicationSet controller for generation errors, confirm all Applications are
healthy, then apply the same change to `platform-gitops/services/labs/`. The `labs` tenant
is applied second to limit blast radius.

The ApplicationSet Watch API and health-field additions become available after the upgrade
as optional future capabilities; no immediate action is required to use them.

## Alternatives

**a. Stay on ArgoCD v3.4.0**

Rejected: v3.4.0 is already the upgrade target of prior proposals, but v3.4.1 includes 150+
additional bug fixes and security improvements. Holding at v3.4.0 indefinitely means missing
those fixes and accepting ongoing label-format ambiguity that will eventually need resolution
anyway when upgrading to any future minor or patch release that also enforces the format.

**b. Upgrade to v3.4.1 without label migration first**

Rejected: high risk. ApplicationSets using old-format labels will stop generating after the
upgrade. While existing Applications are preserved, any new or re-generated Applications
(e.g., after a cluster is added or an ApplicationSet is modified) will fail silently. The
correct sequencing is label migration first, then upgrade.

**c. Switch cluster generator to directory generator**

Rejected by ADR-0001, which mandates the App-of-Apps pattern with cluster generators for
multi-tenant ApplicationSets. A switch to directory generators would require re-architecting
all ApplicationSet templates and is a multi-sprint effort with no direct security benefit.

## Platform impact

**Migrations**

Label changes on cluster Secrets are in-place Kubernetes resource updates — no ArgoCD
restart, no Application deletion. The ApplicationSet controller reconciles immediately upon
detecting the label change.

**Backward compatibility**

ArgoCD v3.4.1 is a patch release on the v3.4 branch. No CRD schema changes are introduced.
Existing Application definitions, sync policies, and RBAC configurations remain valid.

**Resource impact**

No additional memory or CPU usage is expected from this upgrade. The label format change
itself consumes no additional resources. `labs`: no risk — label changes and a controller
image bump do not increase memory consumption.

**Risks and mitigations**

| Risk | Mitigation |
|---|---|
| An ApplicationSet using `kubernetes-version` is missed in the audit | Mandatory grep across all of `platform-gitops/` before upgrade; CI label-format validation added (task T2) |
| ArgoCD upgrade causes unexpected ApplicationSet behavior | Upgrade `admins` first; monitor for 30 minutes before applying to `labs` |
| Label migration itself triggers unexpected reconciliation | Label change on cluster Secrets is additive/update only; existing Applications are not deleted by a label value change alone |
| v3.4.1 introduces a regression not present in v3.4.0 | Rollback procedure via `git revert` restores the previous chart version; existing Applications remain in place |
