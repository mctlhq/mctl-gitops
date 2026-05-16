# TechDocs Path Traversal Fix (CVE-2026-25152)

## Context
CVE-2026-25152 (CVSS 5.3, Moderate) is a symlink path traversal vulnerability in `@backstage/plugin-techdocs-node`. When TechDocs is configured with `techdocs.generator.runIn: local`, the local MkDocs generator follows symlinks inside a service's `docs/` directory. A malicious or misconfigured symlink can cause MkDocs to embed arbitrary host files (e.g., secrets, configuration files) into the generated HTML output, which is then served to authenticated portal users.

mctl-portal uses the TechDocs plugin to render markdown documentation alongside each service in the catalog (see `context/architecture.md`). If the local generator mode is active in any environment, this vulnerability exposes backend file content through the portal UI. The fix is a patch upgrade of `@backstage/plugin-techdocs-node` to version 1.14.1 or 1.13.11, which adds symlink validation before MkDocs is invoked.

## User stories
- AS a platform engineer I WANT `@backstage/plugin-techdocs-node` upgraded to a patched version SO THAT symlinks in docs directories cannot leak host files into generated documentation.
- AS a security team member I WANT confirmation that CVE-2026-25152 is remediated SO THAT the finding is closed in the security tracker.
- AS a developer who publishes service documentation I WANT my existing `docs/` directories and mkdocs.yml files to continue working unchanged SO THAT my documentation is not disrupted.

## Acceptance criteria (EARS)
- WHEN `@backstage/plugin-techdocs-node` is updated THEN THE SYSTEM SHALL resolve to version 1.14.1 or 1.13.11 or later on the matching minor line.
- WHEN the local TechDocs generator processes a `docs/` directory that contains a symlink pointing outside the docs root THEN THE SYSTEM SHALL reject the symlink and log a warning without embedding the linked file content in the generated HTML.
- WHILE TechDocs generates documentation for any catalog entity THEN THE SYSTEM SHALL confine all file reads to the entity's declared docs directory.
- IF `techdocs.generator.runIn` is set to `local` and a symlink traversal is attempted THEN THE SYSTEM SHALL abort the build for that entity and surface an error in the TechDocs build log, not in the generated HTML.
- WHEN a new Docker image is built after the patch THEN THE SYSTEM SHALL pass `yarn audit --level moderate` with no findings attributable to CVE-2026-25152.
- WHEN the patched image is deployed THEN THE SYSTEM SHALL render existing service documentation pages without regression.

## Out of scope
- Changing the `techdocs.generator.runIn` configuration (local vs. docker) — that is a separate operational decision.
- Patching MkDocs itself or its Python dependencies — the fix is in the Node.js wrapper layer.
- Changes to how TechDocs stores or retrieves generated assets (S3, GCS, local storage).
- Updating unrelated TechDocs configuration (search integration, entity kinds filter).
