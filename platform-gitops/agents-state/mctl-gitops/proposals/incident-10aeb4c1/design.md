# Design: incident-10aeb4c1

## Confidence: LOW

## Diagnosis
The KubeDeploymentRolloutStuck alert fired for the mctl-api deployment. mctl-agent had no skill for this signal and the incident record has no evidence or labels. The responder could not read pods or logs: the incident's tenant "mctl-api" is not a registered workspace, and mctl-api is not a service in the "admins" workspace. The platform API deployment is likely managed outside the tenant catalogue (a platform ArgoCD app, related to the separate admins-mctl-api ArgoCD Degraded incident created 13:58Z). No root cause is established. Possible causes are an image pull failure, a failing readiness probe, or resource quota/limits on a new ReplicaSet, but none of these is confirmed.

## Proposed Fix
No change is proposed on the evidence available. The implementer must first verify the live state (ArgoCD app health for admins-mctl-api, deployment conditions, pod events, rollout history). Only if a concrete misconfiguration is found in the mctl-api Helm values in mctl-gitops (image tag, probe path, resource requests/limits) should the single offending field be changed. If the rollout has recovered, make no change.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Do not make any change without verifying the cause first.
