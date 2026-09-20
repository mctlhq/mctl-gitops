# Tasks: incident-f603f940

1. [ ] In `platform-gitops/bootstrap/templates/observability/monitoring.yaml`,
   under `alertmanager.config.route.routes`, add a new route matcher for
   `alertname = "TooHighChurnRate24h"` with `receiver: telegram`, placed
   before the final `receiver: mctl-agent` catch-all route.
2. [ ] Verify the new route does not have `continue: true` (it should stop
   evaluation there, same as `NodeCordoned`/`K3sUpgradeJobFailed`) and does
   not accidentally match any other alertname.
3. [ ] Verify indentation matches the surrounding YAML list (2-space step
   under `routes:`) so the Helm values block for the `monitoring` Argo CD
   Application still parses.
4. [ ] No image tag or other dependent change needed — this is a values-only
   AlertManager config edit.
