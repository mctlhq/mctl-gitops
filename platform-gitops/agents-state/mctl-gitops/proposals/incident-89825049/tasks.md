# Tasks: incident-89825049

1. [ ] Check whether `platform-gitops/services/labs/agent-worker-preview/values.yaml`
       already has a `podAnnotations.rollout-restart-at` entry (may already be applied via
       `incident-cc221e40` or `incident-89825245`). If present and the ArgoCD app
       `labs-agent-worker-preview` is already Healthy, close this proposal as a no-op.
2. [ ] Otherwise, apply the same edit described in design.md.
3. [ ] Verify no other file changed.
4. [ ] Once `labs-agent-worker-preview` is confirmed Healthy, note that issue-305's proposal
       made no state transition this tick and is unaffected by this fix directly — no further
       action needed for it here. A human/operator may re-trigger the shepherd to process it
       cleanly, outside this proposal's scope.
