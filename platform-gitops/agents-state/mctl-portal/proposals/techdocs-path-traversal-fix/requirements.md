# TechDocs Path-Traversal Fix (CVE-2026-23947)

## Context
CVE-2026-23947 was disclosed in `@backstage/plugin-techdocs-node`. When the
TechDocs generator is configured with `techdocs.generator.runIn: local`,
MkDocs follows symlinks inside the documentation source directory. An
attacker who can commit to a documentation repository can craft a symlink
that points to an arbitrary path on the portal host filesystem. The resulting
HTML output is served to all TechDocs viewers, exposing secrets, configuration
files, or other sensitive host content.

mctl-portal runs with `techdocs.generator.runIn: local` (the MkDocs process
runs inside the same container as the backend). The fix is to upgrade
`@backstage/plugin-techdocs-node` to >=1.13.11 or >=1.14.1. This upgrade is
bundled into the Backstage v1.50.3 patch release, which also resolves a
known facets performance regression in the catalog.

## User stories
- AS a platform engineer I WANT the TechDocs generator to reject symlinks
  that escape the docs directory SO THAT host filesystem files cannot be
  embedded in generated TechDocs HTML.
- AS a developer using mctl-portal I WANT my TechDocs pages to continue
  rendering correctly after the upgrade SO THAT my team's documentation is
  unaffected by the security patch.
- AS a security officer I WANT evidence that CVE-2026-23947 is remediated
  SO THAT the finding can be closed in the vulnerability tracker.

## Acceptance criteria (EARS notation)
- WHEN the TechDocs generator processes a documentation source directory
  containing a symlink that resolves outside the docs root THE SYSTEM SHALL
  refuse to follow that symlink and log an error without exposing the target
  file's contents.
- WHEN a legitimate TechDocs page (containing no out-of-tree symlinks) is
  requested THE SYSTEM SHALL generate and serve the HTML without errors.
- WHEN the mctl-portal container image is built THE SYSTEM SHALL include
  `@backstage/plugin-techdocs-node` at version >=1.13.11 (or >=1.14.1 on
  the 1.14.x line).
- WHILE the Backstage v1.50.3 patch upgrade is in progress THE SYSTEM SHALL
  remain available in the existing version until the new image passes all
  smoke tests and is promoted to the `admins` namespace.
- IF the upgraded Backstage version introduces a breaking change detected by
  automated tests THEN THE SYSTEM SHALL halt the deployment and preserve the
  previous running version.

## Out of scope
- Migrating TechDocs to `techdocs.generator.runIn: docker` — a separate
  architectural decision.
- Changes to which repositories are permitted to publish TechDocs — IAM/RBAC
  is out of scope for this patch.
- Upgrading any plugin beyond what is required to reach Backstage v1.50.3.
- Remediation of CVE-2026-29185 (`@backstage/integration`) — tracked under
  `integration-credential-leak-fix`.
