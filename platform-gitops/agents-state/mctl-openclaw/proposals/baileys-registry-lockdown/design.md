# Design: baileys-registry-lockdown

## Current state
The mctl-openclaw workspace (`context/architecture.md`) uses Node.js + TypeScript with an npm workspace layout. The WhatsApp channel is implemented via `@whiskeysockets/baileys` v7.0.0-rc.9, listed as a dependency in `package.json`. The `package-lock.json` records the resolved URL and sha512 integrity hash for installed packages, but no mechanism beyond that prevents a developer or CI pipeline from resolving the package from an alternate registry or from a typosquatted package name if a typo is introduced. The `lotusbail` typosquat (disclosed December 2025, 56,000+ downloads) targets exactly this attack surface. WhatsApp auth tokens are stored in S3 per ADR-0002 and are the highest-value credential in the platform.

## Proposed solution
Two complementary controls are introduced with zero runtime impact:

**Control 1 — Exact version and integrity lock in `package-lock.json`.**
Run `npm install` in a clean environment to ensure `package-lock.json` reflects the current `@whiskeysockets/baileys@7.0.0-rc.9` resolution with its `resolved` URL (`https://registry.npmjs.org/@whiskeysockets/baileys/-/...`) and `integrity` sha512 hash. Commit this lockfile. All subsequent installs (local and CI) must use `npm ci`, which enforces the lockfile exactly and fails if the hash does not match. This is already how npm is supposed to work, but the audit confirms it is correctly in place.

**Control 2 — `.npmrc` registry scope restriction.**
Add or update `.npmrc` at the workspace root to pin the `@whiskeysockets` scope to the official registry:

```
@whiskeysockets:registry=https://registry.npmjs.org/
```

This means even if the global npm config or a compromised environment points to an alternate registry, the `@whiskeysockets` scope is always fetched from `registry.npmjs.org`. Combined with the lockfile integrity check, a substituted package cannot be silently installed.

Optionally, add a CI lint step (e.g., a short shell check or `npm audit` invocation) that asserts the `resolved` field for `@whiskeysockets/baileys` in `package-lock.json` starts with `https://registry.npmjs.org/`. This makes the protection explicit and auditable in CI logs.

This design is chosen because it requires only config-file changes (no new runtime code, no new npm packages), has zero memory impact, and is independently deployable from any version upgrade or broader supply-chain audit work.

## Alternatives

**A. Use a private npm mirror (e.g., Verdaccio) and allowlist only pre-vetted packages.** This provides the strongest supply-chain guarantee but introduces a new infrastructure dependency, requires ongoing maintenance of the mirror, and significantly increases operational complexity. The risk profile of a private mirror failure (npm installs break in CI) is not justified for a single-package hardening action. Dropped for this proposal (appropriate for the broader `npm-supply-chain-audit` effort).

**B. Replace `@whiskeysockets/baileys` with a vendored copy committed to the repository.** Eliminates the registry resolution attack surface entirely. However, vendoring a large npm package with its own dependency tree creates significant maintenance overhead and complicates upstream updates. The integrity-hash approach via `npm ci` provides equivalent protection against substitution at install time without the cost. Dropped.

**C. Add a pre-install script that checks the package name against a denylist.** Catches known typosquats by name (e.g., `lotusbail`) at install time. However, this only catches known names; a new typosquat with an unknown name bypasses it. The scope-pinned `.npmrc` + integrity hash is a stronger, name-agnostic control. Dropped (a denylist check can be added as a supplementary CI lint if desired, but is not the primary control here).

## Platform impact

**Migrations.** None. This change touches only `package.json` (possibly), `package-lock.json` (regenerated/verified), and `.npmrc`. No runtime code changes, no S3 schema changes, no Kubernetes manifests changed.

**Backward compatibility.** Fully backward compatible. `npm ci` already honours the lockfile; the `.npmrc` scope pin does not change which version is installed, only which registry serves it. Existing deployments are unaffected until the next `npm ci` run.

**Resource impact — `labs`.** No memory or CPU impact. This proposal adds no runtime dependencies and changes no deployed code. Risk for `labs`: NONE.

**Risks and mitigations.**
- Risk: The current `package-lock.json` was generated with a different resolved URL than `registry.npmjs.org` (e.g., a GitHub URL or a private mirror). Mitigation: task 1 audits the lockfile before any changes; if a non-standard URL is found, it is treated as a finding requiring investigation before proceeding.
- Risk: The `.npmrc` scope pin breaks a developer workflow that intentionally uses a different registry for a different `@whiskeysockets` package. Mitigation: the scope pin is narrow (`@whiskeysockets` only) and documented; any legitimate override is handled via a per-project `.npmrc` override with justification.
- Risk: A future automated dependency-update tool (e.g., Renovate, Dependabot) modifies the lockfile and inadvertently removes the integrity hash. Mitigation: the CI lint step (task 3) catches this on every PR that touches `package-lock.json`.
