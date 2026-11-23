# Tasks: incident-dcbe4887

1. [ ] Inspect the live diff and PreSync hook state for ArgoCD app admins-mctl-agents-worker to identify what is OutOfSync.
2. [ ] Edit platform-gitops/services/admins/mctl-agents-worker/values.yaml with the minimal change that removes that diff (prepull.ref consistency, or the strategy/rollingUpdate handling).
3. [ ] Verify the change looks correct: image.tag and prepull.ref tag still match, no unrelated fields touched, image tag not bumped.
4. [ ] If no cause can be confirmed, make no change and note that the incident needs human review.
