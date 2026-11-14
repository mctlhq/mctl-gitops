# Tasks: argocd-repo-server-feature-lockdown

- [ ] 1. Audit feature usage across all Apps — DoD: list of users of each feature.
- [ ] 2. Dry-run render with features disabled (depends 1) — DoD: no render errors.
- [ ] 3. Commit argocd-cm changes (depends 2) — DoD: merged, Apps healthy.
- [ ] 4. Remove unneeded SSH proxy settings (depends 1) — DoD: none remain unjustified.

## Tests
- [ ] T1. Every App renders with `argocd app manifests`.

## Rollback
Revert the commit.
