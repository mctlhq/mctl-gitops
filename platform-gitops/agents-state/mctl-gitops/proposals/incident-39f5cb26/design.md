# Design: incident-39f5cb26

## Confidence: LOW

## Diagnosis
mctl-agent had no skill for ArgoCDApplicationDegraded. The application name admins-mctl-api does not resolve: workspace "admins" has no service mctl-api and no ArgoCD application admins-mctl-api was found by the status tool. The alert may be stale, or the application is defined in an ArgoCD project outside the service catalogue. Most likely the Degraded health is the same crash looping mctl-api workload (incident-c2384949). Unverified.

## Proposed Fix
No concrete change. Search mctl-gitops for the Application manifest named admins-mctl-api and compare it with the mctl-api service values. Apply a fix only if a defect (wrong path, image tag, missing secret) is positively identified; otherwise make no change and mark needs-triage.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
