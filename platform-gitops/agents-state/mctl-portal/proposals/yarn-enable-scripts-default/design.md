# Design: yarn-enable-scripts-default

## Current state
mctl-portal uses Yarn Berry (v4.x) as its package manager for a yarn workspaces monorepo
(see `context/architecture.md`): `packages/app`, `packages/backend`, and `plugins/*`. The
current Yarn version is below v4.14.0, so `enableScripts` defaults to `true` — all
postinstall scripts run during `yarn install` without restriction.

Packages known or likely to use postinstall scripts in this monorepo:
- `@playwright/test` / `playwright` — downloads browser binaries on install.
- `@backstage/*` packages with native addon dependencies (e.g., `isolated-vm`,
  `better-sqlite3`) — compile native bindings via `node-gyp`.
- Backstage CLI internal scripts invoked during workspace setup.

The `.yarnrc.yml` file currently does not set `enableScripts` explicitly, relying on the
historical default of `true`.

## Proposed solution
Before upgrading Yarn to v4.14.0+, perform a three-step process:

**Step 1 — Audit.** Run `yarn plugin import @yarnpkg/plugin-nm` (if not already active) and
use `yarn info --all --json | jq '... | select(.scripts)'` (or equivalent) to enumerate all
packages in the current lockfile that declare lifecycle scripts (`preinstall`, `install`,
`postinstall`). Produce a documented list.

**Step 2 — Decide.** For each package in the audit list, make one of two decisions:
  - Mark as **approved**: add it to the `enableScripts` allowlist in `.yarnrc.yml` using the
    `approvedGitRepositories` key (newly available in v4.14.0) or the per-package
    `packageExtensions` mechanism, or set `enableScripts: true` globally if the risk
    assessment concludes that all postinstall scripts in the tree are from trusted publishers.
  - Mark as **blocked**: verify the package works without its install script (e.g., by using
    a pre-built binary or a wasm fallback) and document this.

For mctl-portal's threat model — an internal developer portal with a locked, audited lockfile
and no untrusted third-party plugins — the expected outcome is `enableScripts: true` set
explicitly in `.yarnrc.yml`, making the intent deliberate and documented rather than relying
on a previous default. If the audit reveals any package whose install script origin is unclear,
it is blocked and tracked separately.

**Step 3 — Upgrade Yarn.** Once the `.yarnrc.yml` decision is committed, upgrade Yarn to
v4.14.0 (or v4.14.1 for the Node.js v24 EBADF fix if applicable in future). Run `yarn install`
in CI and confirm all expected binaries and build artifacts are present.

This approach keeps the change auditable: the `.yarnrc.yml` commit is the permanent record
of the security review.

## Alternatives

**1. Set `enableScripts: true` globally without auditing**
The fastest path — matches the previous implicit behaviour. Dropped because it forgoes the
security benefit of the new default and leaves no documented record of which install scripts
are approved. The Yarn team's change signals that the industry is moving toward explicit
allowlisting; ignoring it is a missed hardening opportunity.

**2. Migrate from Yarn Berry to npm workspaces**
npm v10+ also supports workspaces and does not have the `enableScripts` complication.
However, the monorepo's Backstage CLI integration, plugin resolution, and PnP/node_modules
mode are tuned for Yarn. Migration would be high-effort with no direct security or
performance benefit. Dropped.

**3. Pin Yarn to v4.13.x indefinitely**
Avoids the breaking change but accumulates Yarn version debt and misses v4.14.1's EBADF fix
(relevant if Node.js is upgraded to v24 in future). Dropped as a temporary workaround, not
a solution.

## Platform impact

- **Migrations:** `.yarnrc.yml` gains an explicit `enableScripts` setting and optionally an
  allowlist. `yarn.lock` is regenerated after the Yarn version bump. No database or
  Kubernetes manifest changes.
- **Backward compatibility:** Developers with Yarn < v4.14.0 locally will not be affected by
  the `enableScripts` change (old default was `true`). However, `packageManager` field in
  `package.json` (Corepack) should be updated to pin the approved Yarn version, ensuring all
  developers and CI use the same binary.
- **Resource impact (`labs`):** This is a build-time change only. No runtime resources in
  `labs` or `admins` are affected. No `labs` risk.
- **Risks and mitigations:**
  - Risk: a necessary postinstall script is missed in the audit, causing a silent build
    failure (e.g., missing native binary) that only manifests at runtime.
    Mitigation: the CI pipeline must include an explicit smoke test that exercises the
    suspected binary paths (Playwright browser launch, any native addon import) before the
    image is promoted.
  - Risk: `approvedGitRepositories` or other new v4.14.0 config keys are not supported by
    the version of Yarn actually installed via Corepack.
    Mitigation: pin Yarn version via `packageManager` in `package.json` and verify the
    `.yarnrc.yml` syntax against the v4.14.0 release notes before merging.
  - Risk: a future package added to the monorepo has a postinstall script that silently
    fails because no allowlist entry exists.
    Mitigation: the CI `yarn install` output is checked for skip-script warnings (grep for
    `YN0006` or equivalent Yarn warning code) and the build fails if any unapproved script
    was silently skipped.
