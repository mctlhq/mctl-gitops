# Tasks: incident-23f14d57

1. [ ] Locate `platform-gitops/services/labs/mctl-telegram/values.yaml` and confirm the
   actual keys available under the base-service Deployment (readinessProbe,
   minReadySeconds, PodDisruptionBudget). Verify against the current chart
   template before editing, since Confidence is LOW.
2. [ ] Set `minReadySeconds: 10` on the base-service Deployment (both the
   primary and preview release values, if defined separately) so a
   newly-started pod is held out of rotation briefly after passing readiness.
3. [ ] Confirm/raise `readinessProbe.initialDelaySeconds` to at least 5s if it
   is currently lower, so the probe does not pass before the DB retry loop has
   a chance to succeed.
4. [ ] Enable or tighten a PodDisruptionBudget (`maxUnavailable: 1` or less)
   for the base-service Deployment to prevent concurrent restarts of
   primary/preview replicas during rollouts.
5. [ ] Verify the change renders correctly with `helm template` (or the repo's
   equivalent lint/dry-run step) before opening the PR.
6. [ ] No image tag bump needed — this is a values-only change.
