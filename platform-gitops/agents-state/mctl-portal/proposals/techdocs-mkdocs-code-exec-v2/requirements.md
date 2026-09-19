# TechDocs MkDocs Arbitrary Code Execution Fix — CVE-2026-88064 (follow-on hardening)

## Context
CVE-2026-88064 (CVSS 8.8, published 16 Sep 2026) is a newer and more severe
vulnerability in `@backstage/plugin-techdocs-node` than the one already
remediated by `proposals/techdocs-mkdocs-code-exec/` (CVE-2026-29186, CVSS
7.7, fixed at 1.14.3). CVE-2026-88064 shows that the plugin's `mkdocs.yml`
input validation is insufficient across a broader surface than the
plugin/hook allowlist alone: unsafe Python YAML tags, `markdown_extensions`
names/config, theme options, and `extra_templates` can all be abused by an
authenticated user who can register or modify a TechDocs source to reach the
doc generator and execute arbitrary code on the Backstage backend process.
It is fixed only in 1.14.6 and 1.15.4 — both above the 1.14.3 floor that the
prior proposal targets.

Because mctl-portal runs TechDocs for every catalog component and the
backend process shares the Kubernetes service account and Vault token with
the rest of the Backstage backend, this is a critical blast-radius risk for
tenant `admins` (mctl-portal runs only in `admins`; no `labs` interaction).
This proposal is a distinct, higher-severity follow-on to
`proposals/techdocs-mkdocs-code-exec/`: that proposal's 1.14.3 fix remains
necessary but is not sufficient to close CVE-2026-88064. This proposal does
not duplicate or replace the prior one — it supersedes its version floor
(1.14.3 → 1.14.6/1.15.4) and extends its allowlist-style validation to the
additional attack surface identified by this CVE.

## User stories
- AS a platform engineer I WANT `@backstage/plugin-techdocs-node` bumped
  past the CVE-2026-88064 fix versions SO THAT known RCE vectors through
  unsafe YAML tags, `markdown_extensions`, theme options, and
  `extra_templates` are closed.
- AS a security officer I WANT input-validation coverage extended to all
  four attack-surface elements identified by CVE-2026-88064 SO THAT the fix
  is defense-in-depth and not solely reliant on the upstream patched version.
- AS a catalog owner I WANT legitimate `mkdocs.yml` configurations (approved
  extensions, themes, templates) to keep working after the upgrade SO THAT
  my documentation build pipeline is not broken by the hardening.

## Acceptance criteria (EARS)
- WHEN `@backstage/plugin-techdocs-node` is installed, THE SYSTEM SHALL
  report a resolved version of 1.14.6 or higher on the 1.14.x line, or
  1.15.4 or higher on the 1.15.x line, in the lock-file.
- WHEN a TechDocs build is triggered for a component whose `mkdocs.yml`
  contains an unsafe/non-allowlisted Python YAML tag, THE SYSTEM SHALL abort
  the build before YAML deserialization completes and emit an ERROR-level
  log entry, without executing any external process.
- WHEN a TechDocs build is triggered for a component whose `mkdocs.yml`
  declares a `markdown_extensions` entry, theme option, or `extra_templates`
  path that is not on the approved allowlist, THE SYSTEM SHALL reject the
  build with an ERROR-level log entry identifying the offending field.
- WHEN a TechDocs build is triggered for a component with a fully
  allowlist-compliant `mkdocs.yml` (approved YAML tags, extensions, theme
  options, and templates), THE SYSTEM SHALL complete the build and publish
  the rendered docs successfully.
- WHILE a TechDocs build is running, THE SYSTEM SHALL execute MkDocs
  exclusively within the sandboxed build container and not with the
  credentials of the backend service account.
- IF the resolved version of `@backstage/plugin-techdocs-node` in any
  workspace package is below 1.14.6 (on the 1.14.x line) or below 1.15.4
  (on the 1.15.x line), THEN THE SYSTEM SHALL fail the CI dependency-audit
  check.
- IF `proposals/techdocs-mkdocs-code-exec/` has not yet been applied when
  this proposal is picked up, THEN THE SYSTEM SHALL apply both version
  bumps together (1.14.3 fix subsumed by the 1.14.6/1.15.4 target) rather
  than sequencing two separate deploys.

## Out of scope
- File-path traversal hardening (tracked separately in
  `techdocs-path-traversal-fix`).
- Re-deciding the MkDocs allowlist policy itself (security-team decision,
  not an engineering task here) — this proposal only extends *enforcement*
  of validation to the fields named by CVE-2026-88064.
- Upgrading other Backstage plugins not directly related to TechDocs
  (including the unrelated `backstage-1-55-0-scaffolder-recovery-eval`
  minor-version evaluation).
- Adding new TechDocs features or new MkDocs plugin support.
