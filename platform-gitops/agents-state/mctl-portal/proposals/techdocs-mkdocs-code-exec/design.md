# Design: techdocs-mkdocs-code-exec

## Current state
`mctl-portal` runs `@backstage/plugin-techdocs-node` at a version prior to 1.14.3. During a TechDocs build, the plugin invokes `mkdocs build` and passes user-controlled fields from `mkdocs.yml` to the MkDocs process. Versions before 1.14.3 do not fully validate the `plugins` and `hooks` sections against the allowlist before spawning the MkDocs subprocess, allowing injection of arbitrary Python callables via `mkdocs.yml`. The exploit requires only catalog write access (any authenticated user who can open a PR to a catalog component's repo).

The backend pod runs as the `mctl-portal` Kubernetes service account, which holds a Vault token with read access to platform secrets. Successful code execution therefore has full read access to those credentials.

References: `context/architecture.md` — Auth, External integrations sections.

## Proposed solution
Bump `@backstage/plugin-techdocs-node` from its current pinned version to `^1.14.3` in `package.json` within the `packages/backend` workspace. Run `yarn dedupe` to collapse any duplicate transitive copies. The patch in v1.14.3 validates all `plugins` and `hooks` entries in `mkdocs.yml` against the allowlist before constructing the subprocess argument list, and raises a hard error for any unrecognized entry.

No API surface or Backstage configuration changes are required. The fix is purely a dependency version bump with a yarn lock-file update.

Steps:
1. Update `packages/backend/package.json`: `"@backstage/plugin-techdocs-node": "^1.14.3"`.
2. Run `yarn install && yarn dedupe`.
3. Add `npm audit --audit-level=high` (or `yarn audit --level high`) to the CI pipeline gated on the TechDocs build job so future regressions are caught automatically.
4. Validate with the existing Playwright e2e suite and a dedicated security test fixture (see tasks.md).

## Alternatives

**Option A — Disable TechDocs builds entirely until patch ships.**
Eliminates the attack surface immediately but breaks all existing documentation for all catalog services. Unacceptable user impact.

**Option B — Restrict catalog write access to a subset of users.**
Reduces the attacker population but does not eliminate the vulnerability; any permitted contributor could still exploit it. Also, restricting catalog write access is an architectural policy change that requires separate approval. Not a fix.

**Option C — Run MkDocs in a separate, ephemeral Kubernetes Job with no secrets mounted.**
Strong defence-in-depth measure and worth pursuing as a follow-on hardening task, but it is a significant architectural change (async build pipeline, result storage, status reporting). Too much scope for an urgent CVE patch. Record as a future enhancement.

## Platform impact

**Migrations:** None. The dependency bump is backward-compatible; the plugin's public API is unchanged.

**Backward compatibility:** Existing `mkdocs.yml` files that use only allowlisted plugins continue to build without modification. Files that contained exploit payloads will now fail the build with a clear error, which is the desired behaviour.

**Resource impact:** No change to CPU or memory footprint for the `admins` tenant. The `labs` tenant does not run mctl-portal; no labs impact.

**Risks and mitigations:**
- Risk: a legitimate team uses a MkDocs plugin that is not on the allowlist. Mitigation: run a dry-run build against all catalog TechDocs components in the staging environment before promoting to production; report any new build failures and resolve them with the owning team before the production deploy.
- Risk: yarn dedupe introduces an unexpected transitive downgrade. Mitigation: the CI audit step and full Playwright e2e suite catch regressions before merge.
