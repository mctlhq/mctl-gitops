# Catalog Unprocessed Security Patch

## Context
Backstage v1.50.4 was released on April 29, 2026 and includes targeted security fixes for
`@backstage/plugin-catalog-backend-module-unprocessed`,
`@backstage/plugin-catalog-unprocessed-entities-common`, and
`@backstage/plugin-catalog-unprocessed-entities`. These packages are active parts of the
mctl-portal catalog stack. Running an unpatched version violates the platform security SLA and
leaves the service exposed to the vulnerabilities that v1.50.4 was specifically released to fix.

The upgrade stays on the 1.50.x patch line, so there are no breaking API changes and no
community-plugins compatibility window applies. It can be applied simultaneously with the
catalog-facets-perf-fix upgrade (v1.50.3 → v1.50.4 is a single sequential bump).

## User stories
- AS a platform engineer I WANT the catalog backend to run the latest 1.50.x security release
  SO THAT known vulnerabilities in the unprocessed-entities plugin are eliminated.
- AS a security officer I WANT evidence that patched releases are applied promptly
  SO THAT the platform remains compliant with its security SLA.
- AS a developer using the portal I WANT the catalog to remain fully functional after the patch
  SO THAT my day-to-day service browsing is uninterrupted.

## Acceptance criteria (EARS)
- WHEN the Backstage package versions are upgraded to v1.50.4 THE SYSTEM SHALL pass all existing
  catalog integration tests with no regressions.
- WHEN `@backstage/plugin-catalog-backend-module-unprocessed` is at v1.50.4 or later THE SYSTEM
  SHALL report no known CVEs against that package version in the dependency audit.
- WHILE the portal is running after upgrade THE SYSTEM SHALL serve catalog entity pages with
  the same response-time SLOs as before the patch.
- IF a `yarn install` is run against the updated lockfile THE SYSTEM SHALL resolve all
  `@backstage/*` packages to versions within the 1.50.4 release set with no conflicting peer
  dependencies.
- WHEN a new Docker image is built and deployed via ArgoCD THE SYSTEM SHALL start successfully
  and pass the Backstage backend health-check endpoint (`/healthcheck`).

## Out of scope
- Upgrading to Backstage v1.51.x or any next-channel release.
- Changes to catalog-import, scaffolder, techdocs, or any other plugin not in the
  unprocessed-entities module family.
- Addressing CVEs in Node.js, TypeScript, or OS-level packages (covered by separate proposals).
- UI/UX changes to the catalog browsing experience.
