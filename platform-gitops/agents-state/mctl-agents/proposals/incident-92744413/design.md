# Design: incident-92744413

## Confidence: LOW

## Diagnosis
The shepherd step itself succeeded: it deferred the merge of a clean PR (no merge occurred). The workflow was marked Failed only by the post-deploy-verify step, which reported argocd/labs-mctl-telegram as "newly Degraded" after the workflow creation time. That app was already Degraded before this workflow and is unrelated to the proposal being shepherded (it is degraded because the mctl-telegram canary account has "no active session", see incident eb51f2c9). Several shepherd workflows for unrelated services (.github, mctl-agents, mctl-telegram, mctl-api) fail the same way. Likely defect: post-deploy-verify attributes any Degraded app to the workflow, even when no merge happened or the app was Degraded before the workflow started (for example it compares against ArgoCD's refresh/updated timestamp rather than the health-transition time).

## Proposed Fix
In the mctl-agents post-deploy-verify logic: (1) skip the check entirely when the shepherd run did not merge anything (decision defer-merge), and (2) ignore apps whose Degraded health transition predates workflow.creationTimestamp. Locate the script by grepping for "Newly Degraded apps detected".

## Scope
Minimal. Only the post-deploy-verify degraded-app filter. Verify the code before applying; if the logic already compares transition time, make no change.
