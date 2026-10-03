# Tasks: incident-5ae3a90e

1. [ ] In `platform-gitops/services/labs/mctl-telegram/values.yaml`, delete
   the comment block beginning `# One-shot: move the pilot account to Local
   Bridge mode.` together with the `extraObjects` entry it documents (the
   `apiVersion: batch/v1`, `kind: Job`, `metadata.name:
   labs-mctl-telegram-local-mode-flip-1` block and everything nested under
   it), stopping right before the next comment
   `# labs-mctl-telegram-canary-rbac.yaml, which explains why at length.`
2. [ ] Confirm the rest of `extraObjects` still parses as valid YAML (the two
   demo CronJobs above it and the canary CronJob / Middleware / IngressRoute
   below it must be untouched and still present).
3. [ ] No image tag or other dependent change is needed — this is a
   manifest-only removal of an already-completed migration Job.
