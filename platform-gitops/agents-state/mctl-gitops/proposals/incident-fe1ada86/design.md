# Design: incident-fe1ada86

## Diagnosis
The ArgoCD app-of-apps "root-app" has been Degraded for 30 minutes. ArgoCD aggregates child health, so root-app is most likely Degraded because of a degraded child Application, probably the forgejo application (see the related incident bf37f062, forgejo ArgoCDApplicationDegraded, created at the same second). No skill matched and no logs were available. Root cause is unconfirmed.

## Proposed Fix
Do not change root-app itself. Fix the child application (forgejo) per the proposal incident-249e2819; root-app should recover once children are Healthy. If after that root-app is still Degraded, inspect its child Applications in platform-gitops for the unhealthy one.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.

## Confidence: LOW
Hypothesis based on timing correlation only. Verify which child is Degraded before applying anything.
