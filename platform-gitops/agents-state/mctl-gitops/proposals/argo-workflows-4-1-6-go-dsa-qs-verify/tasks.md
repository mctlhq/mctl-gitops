# Tasks: argo-workflows-4-1-6-go-dsa-qs-verify

- [ ] 1. Find deployed Argo Workflows version in gitops manifests — DoD: version recorded.
- [ ] 2. Compare to fixed versions (depends on 1) — DoD: decision noted: close or bump.
- [ ] 3. If needed, bump patch version (depends on 2) — DoD: controller and server updated; CronWorkflows run.

## Tests
- [ ] T1. Submit a test workflow and confirm it succeeds and is archived without NOT NULL errors.

## Rollback
`git revert` the version bump; ArgoCD resyncs the previous version.
