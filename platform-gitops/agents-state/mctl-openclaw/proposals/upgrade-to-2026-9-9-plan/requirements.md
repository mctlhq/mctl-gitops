# Staged upgrade to openclaw 2026.9.9

## Context
Upstream released 2026.9.9 on 2026-10-08. Our deployed version is unclear (`context/current-version.md` says 2026.3.14; earlier research says 2026.7.11-beta.2). Either is behind fixes such as CVE-2026-41336 (fixed in 2026.3.31, CVSS 8.5). 2026.9.9 also has breaking changes: one-way DB format, Telegram `/dashboard` reassignment, `haiku` alias now 5.5, stricter scheduled-job validation.

## User stories
- AS a platform operator I WANT a staged upgrade plan SO THAT security fixes land without breaking `ovk`.
- AS a Telegram user I WANT command changes announced SO THAT I am not surprised by `/dashboard`.

## Acceptance criteria (EARS)
- WHEN the upgrade starts THE SYSTEM SHALL first confirm the deployed version per tenant from gitops and update the version records.
- WHEN a tenant config is older than 2026.9.5 THE SYSTEM SHALL upgrade via 2026.9.5 with `doctor --fix` before 2026.9.9.
- WHEN rolling out THE SYSTEM SHALL proceed `labs` → `admins` → `ovk` with an observation period between stages (ADR-0001).
- WHILE a rollout is in progress THE SYSTEM SHALL pause the s3-sync canary and restart it with a delay afterwards (ADR-0002).
- IF the restore-state probe fails on any tenant THEN THE SYSTEM SHALL halt the rollout before the next tenant.
- IF `labs` memory rises above its pre-upgrade baseline THEN THE SYSTEM SHALL block promotion to `admins`.

## Out of scope
- Merging tenants or skipping `labs` (rejected in ADR-0001).
- Tenant-specific skill changes.
