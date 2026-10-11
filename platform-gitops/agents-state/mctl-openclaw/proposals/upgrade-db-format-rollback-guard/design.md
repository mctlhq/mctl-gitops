# Design: upgrade-db-format-rollback-guard

## Current state
S3 is the source of truth; canary and restore-state probe protect it (ADR-0002). No documented pre-upgrade snapshot step.

## Proposed solution
A runbook step (optionally an Argo workflow) that runs after the canary is paused: server-side copy of the tenant bucket prefix to `snapshots/<date>-<version>/`, then checksum comparison. Rollback restores that prefix and the previous image tag. Snapshots are kept until the tenant has run the new version for the observation period.

## Alternatives
- Bucket versioning only: restore is slower and harder to reason about.
- Skip for `labs`: acceptable only for `labs`, still recommended since it is the canary.

## Platform impact
- Migrations: none.
- Backward compatibility: additive.
- Resource impact: S3 storage only; no pod memory change (safe for `labs`).
- Risks: snapshot of a live bucket may be inconsistent; mitigate by pausing writes via the rollout window.
