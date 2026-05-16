# ArgoCD v3.4.2 Permission Validator Panic and Go Security Updates

## Context
ArgoCD v3.4.2 was released on 2026-05-12. It fixes a permission validator panic
that can crash the ArgoCD server process under specific RBAC evaluation conditions,
making the entire GitOps control plane unavailable until the pod restarts. It also
bundles updated Go runtime binaries that address known Go-level CVEs present in the
v3.4.0 GA release.

The existing `argocd-v3-4-upgrade-plan-v2` proposal targets v3.4.0 as its pinned
version. Shipping v3.4.0 would immediately expose the platform to the known crasher.
This proposal is a focused addendum: change the pinned version in the bootstrap
manifest from v3.4.0 to v3.4.2 before the upgrade is applied. No CRD changes and
no ApplicationSet schema changes exist between these two patch releases.

## User stories
- AS a platform engineer I WANT the ArgoCD deployment to be pinned to v3.4.2 SO
  THAT the production control plane does not crash due to the known permission
  validator panic.
- AS a security engineer I WANT the Go runtime CVEs bundled in v3.4.0 to be
  remediated SO THAT the platform meets its patch-SLA obligations.
- AS an on-call operator I WANT ArgoCD to remain available during normal RBAC
  evaluations SO THAT tenant reconciliation is not interrupted by a recoverable
  software defect.

## Acceptance criteria (EARS)
- WHEN the bootstrap manifest is applied THE SYSTEM SHALL deploy ArgoCD at exactly
  image tag `v3.4.2` (no implicit latest resolution).
- WHEN ArgoCD evaluates any RBAC policy for any tenant THE SYSTEM SHALL not panic
  or exit the server process as a result of permission validator execution.
- WHILE ArgoCD is running at v3.4.2 THE SYSTEM SHALL report no open CVEs
  attributable to the Go runtime vulnerabilities present in v3.4.0.
- IF ArgoCD is already running at v3.4.0 THEN THE SYSTEM SHALL complete an
  in-place rolling update to v3.4.2 without deleting or recreating CRDs.
- WHEN the rolling update is complete THE SYSTEM SHALL resume reconciliation of
  all existing ArgoCD Applications without manual intervention.
- IF the update pod fails its readiness probe within the configured deadline THEN
  THE SYSTEM SHALL automatically roll back to the previous ReplicaSet without
  manual intervention.

## Out of scope
- Any CRD schema changes (none exist between v3.4.0 and v3.4.2).
- ApplicationSet manifest changes (schema is identical across this range).
- Upgrading ArgoCD beyond v3.4.2.
- Changes to RBAC policies themselves — only the ArgoCD binary version is changed.
- Tenant `labs` resource budget — ArgoCD runs in `admins`; labs memory limits are
  unaffected by this change.
- Argo Workflows, Argo Rollouts, or any other Argo project component.
