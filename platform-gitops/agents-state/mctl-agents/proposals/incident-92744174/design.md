# Design: incident-92744174

## Confidence: LOW

## Diagnosis
Same signature as incident argo-mctl-agents-shepherd-6f7d7c9a-1792744413: the shepherd workflow is marked Failed because its post-deploy-verify step reports argocd/labs-mctl-telegram as Degraded. That app has been Degraded since before this workflow ran, because the mctl-telegram canary account has "no active session" (see incident eb51f2c9). It is not a regression introduced by the PR being shepherded. The post-deploy-verify check likely attributes pre-existing Degraded apps to the workflow.

## Proposed Fix
Covered by proposal incident-92744413 in this same service: skip post-deploy-verify when the run merged nothing, and ignore apps Degraded before workflow.creationTimestamp. Implement it once; this proposal needs no separate change beyond confirming the fix covers this case. If incident-92744413 has already been implemented, make no change.

## Scope
Minimal. Only the post-deploy-verify degraded-app filter.
