# Tasks: scaffolder-task-events-ordering-cves

- [ ] 1. Add both CVEs to bundle verification checklist — DoD: checklist updated.
- [ ] 2. Verify installed scaffolder-backend version >= 4.1.0 (depends on bundle merge) — DoD: yarn why output attached.

## Tests
- [ ] T1. Trigger a failing task with a secret parameter; inspect events for leakage.
- [ ] T2. Call task list with an invalid order value; expect 400.

## Rollback
Revert the change PR and redeploy the previous image tag via ArgoCD.
