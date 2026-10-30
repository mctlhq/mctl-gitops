# Design: incident-92750674

## Diagnosis
The shepherd run merged a PR for the .github repo (issue-209), and the post-deploy-verify step then failed because ArgoCD app labs-mctl-telegram was Degraded. That app is unrelated to the merged .github change. The same app is currently failing its canary and alerting (see incident 9c1f8049..., canary session "no active session"), and the step failed identically for another shepherd run (incident ...92750611) on a different PR. The post-deploy-verify step therefore blames any app that is Degraded after the workflow start time, even when the app is degraded for reasons unrelated to the merged change, producing false workflow failures.

## Proposed Fix
In the shepherd post-deploy-verify step, restrict the Degraded check to apps affected by the merged PR (the target service's own ArgoCD app), or ignore apps that were already Degraded or had an active alert before the merge. Exact file location was not verified.

## Confidence: LOW

## Scope
Minimal. Only the post-deploy-verify app selection logic.
