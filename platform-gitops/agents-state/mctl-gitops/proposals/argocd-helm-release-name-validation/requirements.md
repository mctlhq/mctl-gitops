# Audit app names for Argo CD Helm release-name validation

## Context
Argo CD v3.6.3 now requires Helm release names to be valid Helm names (max 53 chars). The `apps` ApplicationSet generates Applications from `services/<tenant>/<svc>/` using `helm-charts/base-service`, so names derive from the directory structure. Any offending name would fail to sync after the upgrade.

## User stories
- AS a platform operator I WANT to know ahead of the upgrade which Applications have invalid release names SO THAT the 3.6.3 rollout does not break syncs.

## Acceptance criteria (EARS)
- WHEN the audit runs THE SYSTEM SHALL list every generated Application name and its derived Helm release name with length and validity.
- IF a release name exceeds 53 characters or is not a valid Helm name THEN THE SYSTEM SHALL report it with a proposed shorter name or an explicit releaseName override.
- WHEN a CI check runs on a PR adding `services/<tenant>/<svc>/` THE SYSTEM SHALL fail if the derived name is invalid.
- WHILE the audit is read-only THE SYSTEM SHALL NOT modify any Application.

## Out of scope
- Renaming existing services without owner approval.
- Changing the ApplicationSet pattern (ADR 0001).
