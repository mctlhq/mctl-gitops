# Design: incident-92264810

## Confidence: LOW

## Diagnosis
The shepherd's own work succeeded: run-shepherd evaluated PR mctl-agents#672, triggered a review-fix, and commit-and-push updated .status.yaml in mctl-gitops. The workflow was marked Failed only because the post-deploy-verify step found argocd/labs-portfolio Degraded after the threshold time (workflow creation, 2026-10-17T19:10:50Z). labs-portfolio (tenant labs, service portfolio) is not the service the shepherd touched (mctl-agents). Current state checked by the responder at 2026-10-17T20:11Z: labs-portfolio is Healthy and Synced (image 0.1.46), and its recent logs show only normal nginx traffic and a graceful rollout shutdown of an old pod. So the Degraded state was transient and unrelated, and the check is too coarse: it attributes any app that became Degraded anywhere since workflow start to this workflow. No incident text asked for any change.

## Proposed Fix
Verify before applying. In the mctl-agents shepherd workflow template's post-deploy-verify step, restrict the Degraded check to ArgoCD apps related to the proposal or PR that was merged (the target service app), or make an unrelated Degraded app a warning in the notification rather than a workflow failure that opens an incident. Locate the step in the shepherd workflow definition (search for "Newly Degraded apps detected"). If that step already scopes by service and the behaviour was a one-off, make no change and close the task as not needed.

## Scope
Minimal. Only the app-selection or failure-severity logic of post-deploy-verify in the shepherd workflow. Do not change shepherd decision logic or labs-portfolio configuration.
