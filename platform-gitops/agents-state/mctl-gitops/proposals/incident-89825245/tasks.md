# Tasks: incident-89825245

1. [ ] Check whether `platform-gitops/services/labs/agent-worker-preview/values.yaml`
       already has a `podAnnotations.rollout-restart-at` entry (it may already be applied via
       `mctl-gitops/proposals/incident-cc221e40/`, which addresses the same root cause). If
       present and the ArgoCD app `labs-agent-worker-preview` is already Healthy, close this
       proposal as a no-op.
2. [ ] Otherwise, apply the same edit described in design.md.
3. [ ] Verify no other file changed.
4. [ ] Once `labs-agent-worker-preview` is confirmed Healthy, note that the shepherd's
       issue-364 proposal itself already merged successfully (only post-deploy-verify
       failed) — no re-run of the implementer is needed for issue-364 itself. A human/operator
       may still want to re-trigger the shepherd tick to clear the fingerprint, but that is an
       operational action outside this proposal's scope.
