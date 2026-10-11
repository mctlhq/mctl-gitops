# Pre-upgrade state snapshot and rollback guard

## Context
openclaw 2026.9.9 states the new DB format cannot be reopened by older versions and downgrade is not supported. Our state lives in S3 per tenant (ADR-0002), so a failed upgrade of `ovk` could leave unrecoverable state without a prior snapshot.

## User stories
- AS an operator I WANT a verified snapshot before each upgrade SO THAT I can roll back `ovk`.

## Acceptance criteria (EARS)
- WHEN an upgrade is about to begin on a tenant THE SYSTEM SHALL copy the tenant's S3 state to a dated snapshot location.
- WHEN a snapshot is taken THE SYSTEM SHALL verify object count and checksums against the source.
- IF verification fails THEN THE SYSTEM SHALL block the upgrade.
- WHILE a snapshot exists for an in-progress upgrade THE SYSTEM SHALL prevent bucket cleanup of it.

## Out of scope
- Replacing S3 as state store (rejected in ADR-0002).
- Changing bucket policies.
