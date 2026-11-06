# Tasks: incident-29ca75a1

1. [ ] Inspect the base-service chart deployment template to find the values key controlling the Deployment strategy.
2. [ ] In platform-gitops/services/admins/mctl-agents-worker/values.yaml, set the strategy to Recreate (or maxSurge 0 / maxUnavailable 1) using the key found in step 1. Leave image.tag at 1.117.0.
3. [ ] If the chart has no strategy knob, instead raise the admins tenant requests.memory quota from 2Gi to 2560Mi and state this in the PR.
4. [ ] Verify with helm template that the rendered Deployment has the new strategy and no other diff.
