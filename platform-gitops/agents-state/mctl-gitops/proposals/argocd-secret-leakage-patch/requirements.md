# Upgrade ArgoCD to v3.3.9 to fix Critical Secret Leakage (CVE-2026-42880)

## Context
CVE-2026-42880 (CVSS 9.6 Critical) is a confirmed vulnerability in ArgoCD versions prior to v3.3.9 and v3.2.11. Any authenticated user can craft a request to the `ServerSideDiff` endpoint that, when the `IncludeMutationWebhook` annotation is present, causes ArgoCD to return plaintext Kubernetes Secret data in the diff response. Because ArgoCD is the sync engine for the entire platform (`ops.mctl.ai`) and holds read access to all tenant secrets across both `admins` and `labs`, this vulnerability directly exposes the full secrets surface of the platform.

A patch is available upstream as v3.3.9. The remediation is a version bump of the ArgoCD Helm chart in this GitOps repository; ArgoCD will then reconcile itself. No schema migration, no new workload, and no additional memory consumption are required.

## User stories
- AS a platform engineer I WANT ArgoCD upgraded to v3.3.9 SO THAT the CVE-2026-42880 attack vector is closed and tenant secrets are no longer extractable via the ServerSideDiff endpoint.
- AS a security officer I WANT evidence that the vulnerable version is no longer running SO THAT the platform passes its next security audit without a critical finding.
- AS a tenant operator I WANT my namespace secrets to remain confidential SO THAT other authenticated ArgoCD users cannot read them through the UI or API.

## Acceptance criteria (EARS)
- WHEN the ArgoCD Helm chart version is updated to v3.3.9 and ArgoCD syncs itself, THE SYSTEM SHALL report all ArgoCD pods running image tag `v3.3.9`.
- WHEN an authenticated user sends a ServerSideDiff request with the `IncludeMutationWebhook` annotation to the patched instance, THE SYSTEM SHALL NOT return plaintext Secret values in the response body.
- WHEN ArgoCD completes the self-upgrade rollout, THE SYSTEM SHALL resume normal Application sync operations with no Applications left in an `Unknown` or `Degraded` state beyond the upgrade window.
- WHILE the ArgoCD upgrade rollout is in progress, THE SYSTEM SHALL continue to serve the ArgoCD UI at `ops.mctl.ai` (read-only access acceptable during restart).
- IF the new ArgoCD pods fail their readiness probe within five minutes of rollout, THE SYSTEM SHALL retain (or automatically restore) the previous pod revision via Kubernetes rolling-update guarantees.

## Out of scope
- Upgrading ArgoCD to a major version (v4.x or beyond).
- Changes to ApplicationSet configuration, sync policies, or RBAC rules beyond what v3.3.9 introduces by default.
- Remediation of any CVE other than CVE-2026-42880 in this proposal.
- Changes to Argo Workflows or External Secrets Operator (covered by separate proposals).
- Hardening the `IncludeMutationWebhook` annotation usage at the application level.
