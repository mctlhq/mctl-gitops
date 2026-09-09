# Tasks: incident-776dd0cd

1. [ ] Locate the Helm values file for the labs tenant's mctl-telegram
   base-service in this repo (should match `image.tag: 0.62.1`,
   `host: tg.mctl.ai`, `port: 8080`, `componentType: base-service`).
2. [ ] Read the current `resources.requests.cpu` / `resources.limits.cpu`
   values for that service. If they look already generous relative to peer
   services, skip step 3 and go to step 4 instead.
3. [ ] Increase `resources.requests.cpu` and `resources.limits.cpu` by
   roughly 30-50% for the labs mctl-telegram base-service.
4. [ ] If HPA/autoscaling is already configured for this service, raise
   `autoscaling.minReplicas` by one instead of (or in addition to) the CPU
   bump.
5. [ ] Verify the edited values file is still valid YAML and the diff is
   scoped only to the labs mctl-telegram base-service resource/autoscaling
   fields.
6. [ ] Note in the PR description that this is a LOW-confidence mitigation
   for MctlTelegramSessionBorrowSlowBurn, and that if the alert continues
   after this change, the next step is a code-level look at the repeated
   OAuth `client_registration` retry traffic from client_name
   `cmg0c9xxt020wec596hjg563i` in the mctl-telegram service itself.
