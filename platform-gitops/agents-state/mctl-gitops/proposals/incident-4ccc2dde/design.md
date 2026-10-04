# Design: incident-4ccc2dde

## Confidence: LOW

## Diagnosis
The ArgoCD Application ovk-openclaw reports health Healthy but syncStatus OutOfSync with an empty revision, persisting over an hour. No pod logs exist in Loki and mctl-agent had no skill for this alert, so no root cause was analysed. The sibling app admins-openclaw shows the identical symptom with the same image tag (2026.7.11-beta.2), which points to a shared cause in the openclaw chart/template (for example a field mutated at runtime by a controller or sidecar that ArgoCD diffs, a rendering error for the per-tenant identity/skills ConfigMaps, or a failed/unresolved revision) rather than a tenant-specific fault. The cause is unverified.

## Proposed Fix
1. Inspect platform-gitops/services/ovk/openclaw/values.yaml and the openclaw chart/template rendering (identity and skills ConfigMaps, per-tenant values) for the diff ArgoCD reports; the empty revision suggests checking the Application's targetRevision and repo path first.
2. If the diff is a runtime-mutated field, add a narrowly scoped ignoreDifferences entry for that exact field on the openclaw Application template. If it is a rendering/values error, fix that value.
3. Do not apply a blanket ignoreDifferences or disable sync policy.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Coordinate with the incident-7a7d1a34 proposal (admins-openclaw), which likely shares the same fix.
