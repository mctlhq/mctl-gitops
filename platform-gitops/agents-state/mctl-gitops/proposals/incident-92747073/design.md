# Design: incident-92747073

## Confidence: LOW

## Diagnosis
The shepherd run itself succeeded: it deferred the merge of mctlhq/.github#213 to a human codeowner and handed nothing off. The workflow was marked Failed only because its post-deploy-verify step found argocd/labs-mctl-telegram Degraded after the 09:54:05Z threshold and still Degraded after the 120s grace. This run merged nothing, so the Degraded app is not caused by it. The same app is flagged on two sibling incidents (incident-92747006, incident-92746868). The service logs show the labs mctl-telegram canary failing every run with "no active session" for user_id 245; that is runtime session state, not a gitops value. The root cause of the Degraded health is not established from the available logs.

## Proposed Fix
Investigate argocd/labs-mctl-telegram health (which resource is Degraded; check the canary CronJob and its session or credential source). Separately, make post-deploy-verify attribute only apps affected by the merged PR's service, or skip when the run performed no merge. Locate the post-deploy-verify step in the shepherd workflow template under platform-gitops and confirm the exact file before editing. Verify before applying.

## Scope
Minimal. Only touch the post-deploy-verify scoping or the single resource that is Degraded.
