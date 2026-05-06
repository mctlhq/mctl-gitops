# ArgoCD Critical Patch: GHSA-3v3m-wc6v-x4x3

## Context
GHSA-3v3m-wc6v-x4x3 is a critical security advisory affecting the ArgoCD server, patched in argo-cd v3.3.9 (released 2026-04-30). The full technical details are not yet publicly disclosed, but the advisory is rated critical and targets the ArgoCD server component. mctl-api depends on ArgoCD: it retrieves an `ARGOCD_TOKEN` from Vault and calls the ArgoCD API to surface application status to the UI, CLI, and AI agents. Any compromise of the ArgoCD server therefore directly threatens the integrity of the deployment pipeline and the status data mctl-api exposes.

The cluster's current ArgoCD version must be confirmed and, if it falls below v3.3.9, an upgrade must be planned and executed. Separately, mctl-api's ArgoCD client calls must be validated for API compatibility with v3.3.9 before the upgrade lands in production. This proposal is distinct from `argocd-token-scope-audit`, which addresses CVE-2025-55190 (token scoping); the two must be tracked independently even though they both concern ArgoCD.

## User stories
- AS a platform engineer I WANT the cluster's ArgoCD server patched to v3.3.9 or later SO THAT the critical vulnerability GHSA-3v3m-wc6v-x4x3 is no longer exploitable in our environment.
- AS a mctl-api developer I WANT confirmation that mctl-api's ArgoCD API calls work correctly against v3.3.9 SO THAT the upgrade does not break application-status delivery to the UI, CLI, or agents.
- AS a security officer I WANT a documented record of exposure window and remediation date SO THAT we can demonstrate compliance in audit logs.
- AS an on-call engineer I WANT a tested rollback path for the ArgoCD upgrade SO THAT a failed upgrade does not take down the deployment pipeline.

## Acceptance criteria (EARS)

### Exposure assessment
- WHEN the exposure-assessment task runs THE SYSTEM SHALL record the currently deployed ArgoCD version and confirm whether it is below v3.3.9.
- IF the deployed ArgoCD version is below v3.3.9 THEN THE SYSTEM SHALL classify the cluster as exposed and block production deploys of unrelated changes until the patch is applied or an explicit risk-acceptance decision is recorded.

### Upgrade
- WHEN ArgoCD is upgraded to v3.3.9 THE SYSTEM SHALL complete without downtime exceeding the agreed maintenance window (30 minutes).
- WHEN the upgrade completes THE SYSTEM SHALL pass all existing ArgoCD health and sync checks in the `admins` namespace.
- WHILE the ArgoCD upgrade is in progress THE SYSTEM SHALL continue to accept mctl-api read requests against cached or last-known application status rather than returning errors to callers.

### API compatibility
- WHEN mctl-api starts against ArgoCD v3.3.9 THE SYSTEM SHALL successfully authenticate using the `ARGOCD_TOKEN` retrieved from Vault and return application status without errors.
- IF any ArgoCD API endpoint used by mctl-api changes its contract in v3.3.9 THEN THE SYSTEM SHALL apply a compatibility shim or updated call before the upgrade reaches production.

### Observability
- WHEN the patch is applied THE SYSTEM SHALL emit a structured audit log entry recording the previous version, new version, timestamp, and operator identity.
- WHILE ArgoCD v3.3.9 is running THE SYSTEM SHALL report a healthy status on the existing `/healthz` probe within 5 minutes of upgrade completion.

## Out of scope
- Remediation of CVE-2025-55190 / `argocd-token-scope-audit` (separate proposal).
- Changes to Vault secret rotation policy or the `ARGOCD_TOKEN` permission model beyond what is required for compatibility with v3.3.9.
- Upgrading ArgoCD past v3.3.9 (e.g., v3.4.x) — this proposal targets the minimum safe version only.
- Any changes to Argo Workflows (`workflows.mctl.ai`), which is a separate Argo project.
- Labs tenant ArgoCD instances, if separate — resource impact of the `labs` tenant is noted in design but operational remediation is out of scope here.
