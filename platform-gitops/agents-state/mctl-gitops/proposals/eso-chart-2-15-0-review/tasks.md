# Tasks: eso-chart-2-15-0-review

- [ ] 1. Read 2.15.0 changelog and CRD diff — DoD: findings written in PR description.
- [ ] 2. Bump chart version if safe (depends on 1) — DoD: all ExternalSecrets Ready.

## Tests
- [ ] T1. ClusterSecretStore `vault-backend` reports Valid after rollout.

## Rollback
`git revert` the chart bump; restore previous CRDs if changed.
