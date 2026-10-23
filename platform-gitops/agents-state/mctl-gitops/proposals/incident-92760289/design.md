# Design: incident-92760289

## Confidence: LOW

## Diagnosis
Same root cause as incident-92761468. Workflow mctl-agents-shepherd-45b8edd1 handled a mctl-agents proposal (issue-758), yet post-deploy-verify failed it because argocd/labs-mctl-telegram, an unrelated app, was Degraded after the grace period. The check is not scoped to the services the run changed. The run-shepherd log was large (45 KB) and was not read in full, so whether a real defect also occurred in that step is unverified.

No instructions were present in the incident data.

## Proposed Fix
1. If not already applied via incident-92761468, scope post-deploy-verify to the ArgoCD apps of the services actually merged by the run, and skip it when nothing merged.
2. Check the run-shepherd step log of mctl-agents-shepherd-45b8edd1 for errors before closing.

## Scope
Minimal. Only the post-deploy-verify gating condition.
