# Tasks: incident-cc221e40

1. [ ] Edit `platform-gitops/services/labs/agent-worker-preview/values.yaml`: add a
       `podAnnotations` block with a `rollout-restart-at` timestamp (see design.md for the
       exact snippet and placement) to force a fresh rollout of the Deployment.
2. [ ] Verify the diff only touches `platform-gitops/services/labs/agent-worker-preview/values.yaml`
       and adds nothing else (no image tag change, no probe/resource change).
3. [ ] After merge, confirm (via `mctl_get_service_status` for team=labs,
       service=agent-worker-preview, or `argocd app get labs-agent-worker-preview`) that the
       Application returns to `Healthy`. If it does not clear within a few minutes of sync,
       flag for human investigation of the resource tree — this fix only addresses a stuck
       rollout, not a genuine code regression in the running image.
