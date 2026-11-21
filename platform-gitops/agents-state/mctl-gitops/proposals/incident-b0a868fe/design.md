# Design: incident-b0a868fe

## Confidence: LOW

## Diagnosis
The root-app ArgoCD application (app-of-apps) has been Degraded for 30 minutes and then also OutOfSync for 1 hour. mctl-agent had no skill for this signal. No service logs are available because argocd is not a tenant workspace. The root cause is not determined. A Degraded app-of-apps usually means one child Application is unhealthy or a manifest in the gitops repo is invalid, for example a recently merged change that fails to render.

## Proposed Fix
Verify before changing anything:
1. Look at the root-app resource tree and conditions to find which child Application is Degraded or failing to sync.
2. Check recent commits to mctl-gitops for the app-of-apps path (the root-app source) that could break rendering (invalid YAML, a duplicate Application name, a missing chart or values file).
3. If a single recent commit is the cause, correct the specific field or revert that commit.
If no concrete cause can be found in the repo, make no change and report this in the PR or issue.

## Scope
Minimal. Only touch the single manifest or value that causes this specific alert. Do not alter ArgoCD project, RBAC or sync policies.
