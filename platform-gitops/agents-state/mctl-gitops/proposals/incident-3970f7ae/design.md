# Design: incident-3970f7ae

## Confidence: LOW

## Diagnosis
KubeQuotaFullyUsed fired from kube-state-metrics for namespace labs-preview, which is the preview namespace paired with tenant "labs". mctl-agent had no skill for this alert and escalated. The tenant lookup for "labs-preview" fails, so service logs could not be read. The main "labs" namespace is not at any hard limit, so the full quota is most likely in the preview namespace, where the likely candidate is a ResourceQuota on pods, requests.memory or persistent storage (starter profile: fixed 256Mi preview requests, no persistent preview disk). Alternatively the alert is transient or stale: the preview namespace may only be at quota while previews are live. The cause could not be confirmed.

## Proposed Fix
The implementer should verify before changing anything:
1. In mctl-gitops, locate the ResourceQuota definition for the labs-preview namespace (tenant provisioning values for "labs").
2. Compare each quota dimension against the live preview workloads. If a dimension is exactly at its hard limit with legitimate workloads, raise that single field modestly.
3. If usage equals the hard limit only because of stale preview releases, make no quota change and instead note that the alert should be tuned (for example, KubeQuotaFullyUsed excluded or given a longer "for" duration on preview namespaces) in the AlertManager rule.

No specific file or value could be determined from the available evidence.

## Scope
Minimal. Only touch the single quota field or alert rule that causes this specific alert.
