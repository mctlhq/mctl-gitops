# ESO Privilege Escalation via Confused-Deputy Patch (CVE-2026-42876)

## Context
CVE-2026-42876 affects External Secrets Operator (ESO) versions 0.1.0 through 2.4.0. A tenant user who holds only `create` permissions on `ExternalSecret` resources can craft a manifest that causes the ESO controller to generate a Kubernetes Secret containing a long-lived Service Account token. Because the controller acts with elevated privileges on behalf of the requesting user, this constitutes a confused-deputy attack: the controller is tricked into performing an action that exceeds the caller's own permission set, potentially enabling cross-tenant privilege escalation.

The platform currently runs ESO via its own Helm chart. The related proposal `eso-cross-namespace-bypass-patch` already targets helm-chart-2.4.1, which remains within the vulnerable range (0.1.0–2.4.0). This proposal supersedes that target by upgrading to ESO v2.5.0, the first release that includes the fix. ESO v2.5.0 ships no CRD schema changes, making the upgrade low-risk from a migration standpoint.

## User stories
- AS a platform operator I WANT ESO upgraded to v2.5.0 SO THAT the confused-deputy privilege-escalation vector described in CVE-2026-42876 is closed before a tenant can exploit it.
- AS a security engineer I WANT all ExternalSecret reconciliation to remain bounded by the requesting tenant's own RBAC SO THAT no tenant can obtain credentials beyond their authorised scope.
- AS a platform operator I WANT the ESO Helm values file updated in GitOps SO THAT ArgoCD reconciles the new version automatically and the upgrade is auditable via git history.

## Acceptance criteria (EARS)

- WHEN the ESO Helm chart version is set to v2.5.0 and ArgoCD syncs successfully THE SYSTEM SHALL report the ESO controller pod running image tag `v2.5.0`.
- WHEN a tenant user with only `ExternalSecret` create permissions submits a manifest designed to trigger the CVE-2026-42876 vector THE SYSTEM SHALL NOT produce a Kubernetes Secret containing a Service Account token beyond that tenant's authorised scope.
- WHEN the ESO controller is running v2.5.0 THE SYSTEM SHALL expose a `/healthz` liveness probe endpoint on the controller pod (feature addition bundled in v2.5.0).
- WHILE ESO v2.5.0 is reconciling existing ExternalSecret manifests in `platform-gitops/argo-workflows/secrets/` THE SYSTEM SHALL continue to synchronise secrets from the `vault-backend` ClusterSecretStore without requiring CRD migrations.
- IF the ArgoCD sync of the ESO application fails THE SYSTEM SHALL leave the previous ESO version running and raise an ArgoCD sync-failure alert.
- WHEN the upgrade is complete THE SYSTEM SHALL pass all existing ExternalSecret integration checks, confirming no regression in secret delivery to tenant namespaces.

## Out of scope
- Upgrading ESO beyond v2.5.0 — only the minimum fix version is targeted here.
- Changes to the `vault-backend` ClusterSecretStore configuration or Vault server (`secrets.mctl.ai`).
- Adding new RBAC policies for tenants — access control tightening beyond the CVE fix is a separate hardening effort.
- Enabling or configuring the new `/healthz` probe in platform alerting — observability wiring is a follow-on task.
- Changes to the `eso-dns-exfil-patch` or `eso-cross-namespace-bypass-patch` proposals — this proposal is an upgrade that supersedes the version target of the latter, but does not alter those documents.
- Memory or resource tuning for the `labs` tenant beyond validating that no additional memory is consumed by the upgrade.
