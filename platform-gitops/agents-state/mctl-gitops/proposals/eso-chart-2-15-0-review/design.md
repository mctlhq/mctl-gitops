# Design: eso-chart-2-15-0-review

## Current state
ESO with Vault `vault-backend` ClusterSecretStore (`context/architecture.md`).

## Proposed solution
Review upstream changelog and CRD diff for 2.15.0 vs the deployed version; bump only if no breaking changes, applying CRDs first when needed.

## Alternatives
- Blind bump: risks secret sync outage.
- Skip: accumulates upgrade debt.

## Platform impact
- Migrations: possible CRD updates.
- Compatibility: unknown until reviewed.
- Resource impact: none expected; minimal for `labs`.
- Risks: secret sync failure; mitigated by staged rollout and revert.
