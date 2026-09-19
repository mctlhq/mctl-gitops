# Design: techdocs-mkdocs-code-exec-v2

## Current state
mctl-portal runs the `techdocs` plugin (see `context/architecture.md`) to
build documentation for every catalog component. Builds are triggered by
the TechDocs backend, which invokes `@backstage/plugin-techdocs-node` to
process each component's `mkdocs.yml` and generate static docs. The
existing proposal `proposals/techdocs-mkdocs-code-exec/` bumps this
dependency to >=1.14.3 and adds an allowlist check limited to MkDocs
plugin/hook directives, addressing CVE-2026-29186. That fix does not cover
the broader input-validation gaps named by CVE-2026-88064: unsafe Python
YAML tags, `markdown_extensions` names/config, theme options, and
`extra_templates`, all of which are parsed from the same untrusted
`mkdocs.yml` before the 1.14.6/1.15.4 patch.

## Proposed solution
1. Bump `@backstage/plugin-techdocs-node` in `packages/backend`'s
   dependency tree to `>=1.14.6` (staying on the 1.14.x line) or `>=1.15.4`
   (if the workspace has already moved to 1.15.x) — whichever keeps
   `yarn.lock` resolution consistent with the rest of the Backstage
   dependency set at bump time.
2. Extend the existing MkDocs config pre-validation step (introduced by
   `techdocs-mkdocs-code-exec`) to reject, before any YAML deserialization
   or MkDocs invocation:
   - Non-allowlisted/unsafe custom YAML tags (`!!python/object`,
     `!!python/name`, etc.) — parse with a safe-only YAML loader instead of
     the default loader.
   - `markdown_extensions` entries not present in a maintained allowlist of
     approved extension names and configs.
   - `theme` options outside an allowlisted key set (block arbitrary
     `custom_dir`/plugin-style theme overrides).
   - `extra_templates` paths that resolve outside the component's declared
     docs root (prevents path-based template injection feeding into code
     execution).
3. Reuse the same sandboxed build-container execution model already
   required by `techdocs-mkdocs-code-exec` (MkDocs runs without backend
   service-account credentials) — no new sandboxing architecture is
   needed, only the additional field-level checks above.
4. Keep the CI dependency-audit gate from the prior proposal, updating its
   version floor from 1.14.3 to 1.14.6/1.15.4.

## Alternatives
- **Wait for a future Backstage minor/major and let the fix ride along**:
  rejected — CVSS 8.8 with confirmed RCE is too high-severity to defer
  until the next scheduled version bump; ADR 0001's "wait ~a week"
  guardrail is for feature/major releases, not for an already-published
  high-severity CVE fix.
- **Disable TechDocs builds entirely until a full plugin sandbox rewrite**:
  rejected — over-broad; would remove documentation functionality for
  every catalog component and is disproportionate given a targeted,
  already-published upstream fix exists.
- **Only extend input validation, skip the version bump**: rejected —
  the upstream fix at 1.14.6/1.15.4 addresses code paths inside the plugin
  itself that a backend-side pre-validation layer cannot fully cover
  (defense-in-depth only works alongside the patched version, not instead
  of it).

## Platform impact
- **Migrations**: none — this is a dependency version bump plus additive
  validation logic; no data schema changes.
- **Backward compatibility**: allowlist-compliant `mkdocs.yml` files
  continue to build unchanged. Components using previously-unvalidated but
  legitimate `markdown_extensions`/theme options may need their config
  added to the allowlist — track any such cases as a fast-follow allowlist
  update, not a blocker to shipping the security fix.
- **Resource impact**: negligible; validation runs are lightweight
  YAML/config parsing before build. Scoped entirely to tenant `admins`
  (mctl-portal runs only in `admins`); no impact on `labs`.
- **Risks and mitigations**:
  - Risk: overly strict allowlist breaks legitimate docs builds.
    Mitigation: stage the allowlist rollout behind a warn-only mode for one
    cycle before hard-enforcing rejection, and monitor build failure rates.
  - Risk: version bump introduces an unrelated regression from other
    1.14.6/1.15.4 changes. Mitigation: smoke-test TechDocs builds for a
    representative sample of catalog components in a lower environment
    before promoting to production.
