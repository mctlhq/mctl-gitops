# Design: incident-13d41316

## Confidence: LOW

## Diagnosis
The alert fires when the vault StatefulSet has ready replicas different from desired replicas, or an update has not fully rolled out. No logs were returned for vault/vault, so the root cause (non-ready pod, failing readiness probe such as a sealed Vault, unbound PVC, or a stuck revision) could not be determined independently. The matched skill returned only a MEDIUM-confidence, non-fixable diagnosis. A sealed Vault after restart is a plausible cause, since sealed pods fail readiness, but this is unverified.

## Proposed Fix
No concrete change is justified by the evidence. The implementer should first inspect the vault Helm values under platform-gitops (vault service values.yaml): replica count, readinessProbe, PVC/storage settings, resource limits and any recently changed image tag. Apply a change only if a clear misconfiguration is found there (for example a recent image tag or probe change coinciding with 2026-10-25T21:18Z). If nothing is found, make no change and note that the alert needs operator investigation (possibly a manual unseal), which is not a GitOps fix.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Do not change secrets, policies or network rules.
