# Design: incident-adc1093c

## Confidence: LOW

## Diagnosis
The alert KubeDeploymentRolloutStuck fired for deployment mctl-api in namespace/tenant mctl-api. mctl-agent had no skill for it. The responder could not observe the workload: the platform API reports "tenant not found: mctl-api" and the admins workspace has no catalogued mctl-api service, so no pod state, events or logs were available. The root cause is unknown. Likely candidates are an image pull failure, a failing readiness probe, or quota exhaustion in the namespace. A related incident (ArgoCD app admins-mctl-api Degraded) exists for the same component and was too recent to process in this run.

## Proposed Fix
No concrete change can be justified from available evidence. The implementer must first verify:
1. Whether platform-gitops contains a mctl-api service definition and which values (image tag, resources, probes) it sets.
2. Whether the referenced image tag exists in the registry.
3. Whether the alert is stale (the rollout has since completed), in which case no change is needed and the PR should be a no-op.
Apply a change only if one of these checks shows a concrete misconfiguration.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
