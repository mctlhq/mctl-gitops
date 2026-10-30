# Design: incident-92750611

## Diagnosis
This is the same failure pattern as incident argo-mctl-agents-shepherd-4a335fef-1792750674 (proposal incident-92750674). The shepherd merged a PR for issue-716 (mctl-telegram, so possibly related to labs-mctl-telegram), and post-deploy-verify reported labs-mctl-telegram Degraded. Because the other shepherd run, which merged an unrelated .github change, saw the same degraded app, and because the canary was failing with "no active session" for the canary account while real-user calls succeeded, the degradation is more likely pre-existing than caused by either merge. This one could be a genuine regression, so it cannot be fully ruled out.

## Proposed Fix
Same as incident-92750674: make post-deploy-verify distinguish apps degraded before the merge from newly degraded apps caused by it. Additionally, for this run, check whether the mctl-telegram change from issue-716 is healthy (pods Ready, no crash loops) before concluding.

## Confidence: LOW

## Scope
Minimal. Only the post-deploy-verify selection logic; do not revert the merged PR without evidence.
