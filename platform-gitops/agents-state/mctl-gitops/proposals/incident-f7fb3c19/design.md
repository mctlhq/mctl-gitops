# Design: incident-f7fb3c19

## Confidence: LOW

## Diagnosis
The root-app ArgoCD application (app-of-apps) has been Degraded for 30 minutes. mctl-agent has no skill for argocd_app_degraded, and no service logs exist for the argocd pseudo-tenant, so the root cause was not observed directly. An app-of-apps is Degraded when one or more child Applications are Degraded (failed rollout, bad Helm values, missing CRD or secret, or a failed sync hook). The offending child is unknown from the available evidence. This diagnosis is a hypothesis, not a confirmed finding.

## Proposed Fix
Investigate before changing anything:
1. Identify which child Application of root-app is Degraded (ArgoCD status, or mctl_list_services for the affected tenants).
2. Read that child's resource health message and its pod state or recent events.
3. Fix the single offending field in mctl-gitops (for example a bad Helm value, resource limit or image tag) in the child's values or manifest.
If no child is unhealthy now, the alert was transient. In that case make no change, and note that in the PR or task result.

## Scope
Minimal. Only touch the single field or rule that causes the degraded child. Do not change root-app itself, ArgoCD project settings, or sync policy unless the evidence points there.
