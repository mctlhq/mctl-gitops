# Design: incident-c2384949

## Confidence: LOW

## Diagnosis
mctl-agent had no skill for KubePodCrashLooping and collected no analysis. Logs and pod state could not be read: the platform reports no tenant named "mctl-api" (mctl-api is a platform service, not a tenant workspace). No root cause was observed. The three related incidents (rollout stuck, ArgoCD degraded for admins-mctl-api and root-app) are probably symptoms of the same crash-looping mctl-api pod, but this is unverified.

## Proposed Fix
No concrete change can be named from the available evidence. The implementer must first inspect the mctl-api Deployment values under platform-gitops/services/ in mctl-gitops, and recent commits to them (a bad image tag, missing env var/secret, or too-low memory limit are the usual causes). Apply a fix only if a defect is positively identified in the repository; otherwise make no change and report needs-triage.

## Scope
Minimal. Only touch the single field that causes this specific alert.
