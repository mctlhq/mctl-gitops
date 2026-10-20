# Design: incident-487ba481

## Confidence: LOW

## Diagnosis
The alert fires when the vault StatefulSet in namespace vault has ready replicas different from desired replicas. mctl-agent's statefulset-replicas-mismatch skill produced only a MEDIUM-confidence diagnosis with fixable=false, so no PR was made. The responder found no log lines for vault/vault in Loki and has no cluster access, so the actual cause (not-ready pod, readiness probe failure such as a sealed Vault, unbound PVC, or a stuck revision rollout) is not established. Vault commonly reports not-ready while sealed, which a values change cannot fix. The alert occurred once (occurrence_count 1) and may have been a transient rollout.

## Proposed Fix
No speculative config change. The implementer should first verify the current state in mctl-gitops: inspect platform-gitops/services for the vault StatefulSet values (replicas, readinessProbe, resources, persistence) and any recent commits that touched them. Only if a concrete misconfiguration is found (for example replicas value vs. available PVC/node capacity, or a probe path that cannot succeed) change that single field. If nothing is found, make no change and record in the PR/notes that the incident appears transient or requires operator action (unseal or pod recreation), which is outside GitOps scope.

## Scope
Minimal. Do not delete pods, change secrets, unseal, or alter policies. Only touch a single field that is demonstrably the cause.
