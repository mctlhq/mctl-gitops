# Catalog Facets Performance Fix

## Context
Backstage v1.50.3 (released April 22, 2026) resolves a confirmed performance regression in
the catalog facets endpoint. This endpoint backs the search and filter UI used by every
developer on the mctl-portal platform: kind filters, owner filters, lifecycle filters, and
tag facets all route through it. Under load the regression increases backend CPU consumption
and raises p95 response latency for catalog browsing queries, degrading the primary way
developers discover and navigate services.

The fix is a patch-level bump on the 1.50.x line — no breaking changes, no new configuration
required. Because v1.50.4 (the security patch in proposal `catalog-unprocessed-security-patch`)
is a superset of v1.50.3, both improvements are captured in a single upgrade step to v1.50.4,
reducing deployment overhead.

## User stories
- AS a developer browsing the service catalog I WANT facet filters to respond quickly SO THAT
  I can find services without noticeable lag.
- AS a platform engineer I WANT the catalog backend CPU usage to return to pre-regression
  levels SO THAT I can maintain the existing resource allocation without adding capacity.
- AS an on-call engineer I WANT the facets endpoint latency to be within SLO SO THAT
  catalog-related alerts do not fire under normal load.

## Acceptance criteria (EARS)
- WHEN a catalog facets query is issued after the upgrade THE SYSTEM SHALL respond with p95
  latency no worse than the pre-regression baseline measured before v1.50.x introduced the
  regression.
- WHILE the portal is serving normal developer traffic after upgrade THE SYSTEM SHALL NOT
  exhibit CPU spikes on the backend pod attributable to catalog facet queries above the
  pre-regression baseline.
- WHEN all `@backstage/*` packages are at v1.50.3 or later THE SYSTEM SHALL serve the
  catalog search/filter UI with facets populated correctly for kind, owner, lifecycle, and
  tag dimensions.
- IF the facets endpoint receives concurrent requests from multiple users THE SYSTEM SHALL
  process them without error (no 5xx responses) and within the configured backend request
  timeout.
- WHEN the upgraded image is deployed via ArgoCD THE SYSTEM SHALL pass the backend
  health-check (`/healthcheck`) and the catalog entity count SHALL remain consistent with
  the pre-deploy baseline.

## Out of scope
- Rewriting the facets query logic beyond what v1.50.3 provides.
- Changes to the search plugin or full-text index.
- Changes to catalog-import, scaffolder, techdocs, or other plugins.
- Adding new facet dimensions or UI filter controls.
- Addressing security CVEs (covered by the companion `catalog-unprocessed-security-patch`
  proposal).
