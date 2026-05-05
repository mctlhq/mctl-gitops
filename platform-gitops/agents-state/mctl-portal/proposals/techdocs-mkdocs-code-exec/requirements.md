# TechDocs MkDocs Arbitrary Code Execution Fix

## Context
CVE-2026-29186 (GHSA-928r-fm4v-mvrw, CVSS 7.7 High) affects `@backstage/plugin-techdocs-node` prior to v1.14.3. Any authenticated user who can push a `mkdocs.yml` to a catalog component repository can craft a config that escapes the plugin's allowlist and triggers arbitrary Python code execution on the Backstage backend process during a TechDocs build.

mctl-portal runs TechDocs builds for every service in the catalog. Because the backend process shares the same Kubernetes service account and Vault token used by the broader Backstage backend, a successful exploit grants the attacker access to all secrets and downstream APIs (mctl-api, Argo Workflows, Vault). This is a critical blast-radius risk for the `admins` tenant.

## User stories
- AS a platform engineer I WANT the TechDocs build pipeline to reject MkDocs config directives outside the approved allowlist SO THAT a malicious contributor cannot execute arbitrary code on the Backstage backend.
- AS a security officer I WANT confirmation that `@backstage/plugin-techdocs-node` is at v1.14.3 or later in production SO THAT CVE-2026-29186 is provably remediated.
- AS a catalog owner I WANT TechDocs builds to continue working for legitimate documentation SO THAT I do not lose access to my service docs after the patch.

## Acceptance criteria (EARS)
- WHEN `@backstage/plugin-techdocs-node` is installed, THE SYSTEM SHALL report version 1.14.3 or higher in the resolved lock-file.
- WHEN a TechDocs build is triggered for a component whose `mkdocs.yml` contains a plugin or hook directive not present in the Backstage allowlist, THE SYSTEM SHALL abort the build and emit an error log entry at level ERROR without executing any external process.
- WHEN a TechDocs build is triggered for a component with a valid, allowlist-compliant `mkdocs.yml`, THE SYSTEM SHALL complete the build and publish the rendered docs successfully.
- WHILE a TechDocs build is running, THE SYSTEM SHALL execute MkDocs exclusively within the sandboxed build container and not with the credentials of the backend service account.
- IF the resolved version of `@backstage/plugin-techdocs-node` is below 1.14.3 in any workspace package, THEN THE SYSTEM SHALL fail the CI build with a dependency-audit error.

## Out of scope
- File-path traversal hardening (addressed in the separate `techdocs-path-traversal-fix` proposal).
- Changes to the MkDocs allowlist policy itself (allowlist content is a security-team decision, not an engineering task here).
- Upgrading other Backstage plugins not directly related to TechDocs.
- Adding new TechDocs features or MkDocs plugin support.
