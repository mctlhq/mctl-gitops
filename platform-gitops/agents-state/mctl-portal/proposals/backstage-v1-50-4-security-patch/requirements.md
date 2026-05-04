# Backstage v1.50.4 Catalog Security Patch

## Context
The Backstage project released v1.50.4 as a targeted patch addressing CVEs in the `catalog-unprocessed-entities` package family. mctl-portal's service catalog is a core feature relied upon by all platform tenants for service discovery, ownership tracking, and scaffolder-driven onboarding. The catalog backend uses the affected package family, meaning the disclosed vulnerabilities are present in the current production deployment.

Because this is a patch release (not a minor or major), it does not trigger the platform's ADR wait period for Backstage upgrades. The release additionally incorporates the v1.50.3 facets-endpoint performance improvement, which reduces catalog query latency for large entity sets. Remaining on the pre-patch version exposes the catalog backend to the disclosed CVEs and forgoes an available performance improvement.

## User stories
- AS a platform security officer I WANT mctl-portal's Backstage packages updated to v1.50.4 SO THAT the CVEs affecting the catalog-unprocessed-entities package family are remediated.
- AS a portal user I WANT the catalog facets endpoint to respond faster after the upgrade SO THAT browsing and filtering the service catalog is more responsive under load.
- AS a portal engineer I WANT the patch applied through the standard Backstage version-bump workflow SO THAT the upgrade is consistent with past patch upgrades and does not require custom migration steps.

## Acceptance criteria (EARS)
- WHEN all Backstage core packages are updated to v1.50.4 THE SYSTEM SHALL report no known CVEs against the `catalog-unprocessed-entities` package family in the CI security audit.
- WHEN the updated backend is deployed THE SYSTEM SHALL load and process the full service catalog without errors.
- WHEN a catalog facets query is executed THE SYSTEM SHALL return results; performance at or better than the pre-upgrade baseline is expected per the v1.50.3 improvement.
- WHILE the rolling update is in progress THE SYSTEM SHALL keep at least one healthy catalog backend pod available to serve catalog API requests.
- IF the Backstage version bump introduces a dependency conflict with an existing plugin THE SYSTEM SHALL surface the conflict as a build or type-check failure in CI before deployment.
- WHEN the patched image is deployed to the `admins` tenant THE SYSTEM SHALL pass all existing catalog integration tests with no regressions.
- IF the deployment health check fails after rollout THE SYSTEM SHALL remain on the previous version until the failure is investigated.

## Out of scope
- Upgrading to Backstage v1.51.x or later — this proposal covers the v1.50.4 patch only.
- Changes to catalog-info.yaml files, entity processors, or ingestion pipelines.
- Performance tuning beyond what is delivered by the upstream v1.50.3/v1.50.4 patch.
- Any changes to the `labs` tenant workloads.
- Modifications to custom plugins (`plugins/*`) unless required to resolve a type-check error introduced by v1.50.4.
