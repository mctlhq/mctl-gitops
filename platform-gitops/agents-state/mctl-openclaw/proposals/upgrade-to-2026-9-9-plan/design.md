# Design: upgrade-to-2026-9-9-plan

## Current state
Three separate tenants with S3 state, canary and restore-state probe (`context/architecture.md`, ADR-0001, ADR-0002). Deployed version must be re-verified.

## Proposed solution
Bump the image tag in mctl-gitops per tenant, in order, with a gated checklist:
1. Verify versions; take the S3 snapshot (see `upgrade-db-format-rollback-guard`).
2. If older than 2026.9.5, run the intermediate upgrade with `doctor --fix`.
3. Review config for breaking changes: pin the Haiku model explicitly if 4.5 is required; announce `/controlui`; audit scheduled jobs for failing reset targets.
4. Roll out `labs`, observe (memory, canary, probe), then `admins`, then `ovk`.
5. Update `context/current-version.md` and add an ADR (done by a human, since `context/` is read-only for the agent).

## Alternatives
- Stay on current version and patch individually: rejected, the CVE backlog is large.
- Go straight to `ovk`: rejected by ADR-0001.
- Pin to an LTS train: viable if one exists; evaluate in task 1.

## Platform impact
- Migrations: DB format is one-way.
- Backward compatibility: Telegram command change, model alias change.
- Resource impact: `labs` memory must be measured; release notes suggest a reduction, not an increase.
- Risks: `ovk` auth loss (mitigated by snapshot + probe), canary false alerts (pause canary).
