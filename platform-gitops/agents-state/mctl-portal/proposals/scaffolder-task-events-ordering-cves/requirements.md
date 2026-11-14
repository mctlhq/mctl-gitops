# Cover CVE-2026-106502 and CVE-2026-106506 in the scaffolder patch

## Context
Two further scaffolder-backend advisories (task failure event leakage, task list ordering validation) are fixed in 4.1.0 but are not listed in the existing security bundle. The scaffolder is tied to mctl-gitops.

## User stories
- AS a platform admin I WANT Cover CVE-2026-106502 and CVE-2026-106506 in the scaffolder patch SO THAT the portal stays secure and stable.

## Acceptance criteria (EARS)
- WHEN the portal is deployed THE SYSTEM SHALL run @backstage/plugin-scaffolder-backend >= 4.1.0.
- WHEN a scaffolder task fails THE SYSTEM SHALL NOT include sensitive values in failure events.
- IF a task list request has an invalid order parameter THEN THE SYSTEM SHALL reject it.

## Out of scope
- Backstage major upgrades; changes outside agents/mctl-portal.
