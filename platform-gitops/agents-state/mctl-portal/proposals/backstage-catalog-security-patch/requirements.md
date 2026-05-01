# Backstage v1.50.4 Security Patch for Catalog Plugins

## Context
On April 29, 2026 the Backstage project released v1.50.4, a security-only patch targeting vulnerabilities in three catalog plugin packages: `plugin-catalog-backend-module-unprocessed`, `plugin-catalog-unprocessed-entities-common`, and `plugin-catalog-unprocessed-entities`. All three packages are part of the active plugin set used by mctl-portal. Running un-patched catalog plugins exposes the service to the disclosed vulnerabilities, which could affect component registration integrity and backend processing pipelines.

ADR-0001 mandates waiting approximately one week after a Backstage release before deploying, to allow the `backstage/community-plugins` ecosystem to catch up and avoid breaking compatibility with dependent plugins. The release was published on April 29, 2026; the earliest acceptable deployment date is therefore May 6, 2026. This proposal captures the requirements to schedule, validate, and ship this patch safely within that constraint.

## User stories
- AS a platform engineer I WANT the catalog plugin packages updated to v1.50.4 SO THAT known security vulnerabilities are remediated before they can be exploited.
- AS a developer I WANT the catalog, catalog-import, and unprocessed-entities views to remain fully functional after the upgrade SO THAT my day-to-day service discovery workflows are not disrupted.
- AS a security officer I WANT an auditable record of when the patch was applied and verified SO THAT I can demonstrate timely remediation in compliance reviews.
- AS a platform engineer I WANT the upgrade gated behind a compatibility window SO THAT community-plugins breakage does not cause a production incident.

## Acceptance criteria (EARS)

- WHEN the deployment is triggered, THE SYSTEM SHALL reject any rollout attempted before 2026-05-06T00:00:00Z by enforcing the minimum-date gate in the ArgoCD Application sync window.
- WHEN the Backstage backend pod starts after the upgrade, THE SYSTEM SHALL complete catalog ingestion of all registered components within 5 minutes without errors logged at WARN level or above in the catalog processor pipeline.
- WHEN a user navigates to the Catalog page in the portal, THE SYSTEM SHALL render the component list with no degraded or missing entries compared to the pre-upgrade baseline snapshot.
- WHEN the unprocessed-entities plugin endpoint is called, THE SYSTEM SHALL return HTTP 200 with a valid JSON body containing the expected schema fields.
- WHILE the upgrade is in progress and the pod is restarting, THE SYSTEM SHALL serve existing catalog reads from the surviving pods with no HTTP 5xx responses to end users (rolling-update strategy, minAvailable=1).
- IF a community-plugins compatibility issue is detected during the staging validation run, THEN THE SYSTEM SHALL block promotion to production and create a Jira ticket referencing the failing plugin and the relevant Backstage issue tracker entry.
- IF the Backstage backend fails its liveness probe within 3 minutes of starting the new image, THEN THE SYSTEM SHALL automatically roll back to the previous image tag via the ArgoCD self-heal mechanism.
- WHEN the patched image is deployed to production, THE SYSTEM SHALL report no new CVEs in the catalog plugin packages as confirmed by a `yarn audit` run with exit code 0 (no high/critical advisories).

## Out of scope
- Upgrading any Backstage packages beyond the catalog plugin family targeted by v1.50.4 (scaffolder, kubernetes, techdocs, search, github-actions, observability plugins are not part of this patch).
- Changes to the Dex JWT authentication flow or session storage.
- Any Node.js runtime version change.
- Modifications to the RBAC/permissions framework or group mappings.
- Infrastructure changes to nginx, Docker base image, or ArgoCD configuration unrelated to the image tag bump.
- Remediation of any vulnerabilities outside the three catalog plugin packages listed above.
