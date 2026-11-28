# Bump Backstage backend packages to patched versions (Oct 2026 CVE batch)

## Context
Eight medium-severity advisories were published on 6-7 Oct 2026 against Backstage backend packages we run: catalog-backend (CVE-2026-106496, -106498), scaffolder-backend (-106502, -106504, -106506), kubernetes-backend (-106561) and proxy-backend (-106491). Scaffolder task logs/events can leak credentials, and the kubernetes plugin can return values meant to be masked.

Fixed versions: catalog-backend >=3.9.1, scaffolder-backend >=4.1.0, kubernetes-backend >=0.21.9, proxy-backend >=0.6.17 (Backstage release line v1.54.6+). Several earlier proposals touch parts of this; this one is the consolidated verification and bump.

## User stories
- AS a platform admin I WANT patched backend packages SO THAT credentials in scaffolder output and k8s data are not exposed to authenticated users.
- AS a developer I WANT the upgrade to be non-breaking SO THAT onboarding via the scaffolder keeps working.

## Acceptance criteria (EARS)
- WHEN the portal image is built THE SYSTEM SHALL resolve catalog-backend >=3.9.1, scaffolder-backend >=4.1.0, plugin-kubernetes-backend >=0.21.9 and proxy-backend >=0.6.17.
- WHEN a user reads scaffolder task logs or events THE SYSTEM SHALL NOT return backend-managed secret values.
- WHEN a user with kubernetes read permission queries resources THE SYSTEM SHALL return masked values for sensitive fields.
- WHEN a proxy request path escapes the configured base path THE SYSTEM SHALL reject it.
- IF any package resolves below its fixed version THEN THE SYSTEM SHALL fail the CI audit check.
- WHILE the upgrade is rolling out THE SYSTEM SHALL keep Dex login and the observability plugin functional.

## Out of scope
- Backstage major upgrade; Bitbucket Server module (not used); the 1.57.x minor upgrade.
