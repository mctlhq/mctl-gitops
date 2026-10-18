# Investigate mctl-web OutOfSync state

## Context
On 2026-10-17 ArgoCD app admins-mctl-web reports Healthy but OutOfSync with imageTag 7.8.0; it was Synced on 2026-09-26 at 7.5.3.

## User stories
- AS an operator I WANT to know why the app is OutOfSync SO THAT drift is resolved or documented.

## Acceptance criteria (EARS)
- WHEN the investigation runs THE SYSTEM SHALL identify the diff between desired and live state using read-only tools.
- IF the cause is persistent drift THEN THE SYSTEM SHALL record the cause and a remediation in a follow-up change.
- WHILE investigating THE SYSTEM SHALL NOT perform write operations against mctl.

## Out of scope
- Version doc reconciliation and host drift (existing proposals).
