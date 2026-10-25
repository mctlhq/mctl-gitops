# Design: incident-e094ddb9

## Confidence: LOW

## Diagnosis
The vault StatefulSet reported ready replicas not equal to desired replicas
(rollout not complete). Loki returned no log lines for vault/vault, so the
cause could not be independently observed. Plausible causes: a Vault pod
sealed or not passing its readiness probe (Vault pods are commonly not Ready
while sealed), a pending PVC, or a stuck rollout after a chart/values change.
The skill was MEDIUM confidence and not marked auto-fixable. The alert may
also have been transient and already cleared.

## Proposed Fix
No concrete change is identified. The implementer must first verify current
state: check whether the alert is still firing and the vault StatefulSet is
still unready, and review recent commits to the vault values under
platform-gitops/ (image tag, resources, readinessProbe, persistence size).
If a recent values change is the cause, revert or correct that single field.
If the pods are only sealed or the alert has cleared, make no change and
record that in the PR/notes. Do not delete pods or unseal Vault via this
proposal.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
