# Tasks: incident-2932eaa0

1. [ ] Verify which resource inside the ArgoCD Application `labs-mctl-telegram`
   is reporting Degraded health (ArgoCD UI resource tree, or
   `kubectl -n labs describe job labs-mctl-telegram-local-mode-flip-1` /
   `kubectl -n labs get job,pods -l app.kubernetes.io/instance=labs-mctl-telegram`).
2. [ ] If it is the `labs-mctl-telegram-local-mode-flip-1` Job that failed or
   exhausted its retries, remove that Job block from
   `platform-gitops/services/labs/mctl-telegram/values.yaml` (`extraObjects`)
   so ArgoCD prunes it and the Application's health clears.
3. [ ] If it is a different resource, do NOT remove the Job — instead record
   the actual failing resource/condition for a follow-up fix; this proposal's
   change does not apply.
4. [ ] After the change syncs, confirm `labs-mctl-telegram` reports
   health=Healthy (e.g. via the platform's service-status check).
