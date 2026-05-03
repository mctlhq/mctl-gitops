# Yarn enableScripts Default Change Evaluation

## Context
Yarn Berry v4.14.0 (released April 16, 2026) changed the default value of `enableScripts`
from `true` to `false`. This means that from v4.14.0 onward, any project that upgrades Yarn
without explicitly setting `enableScripts: true` (or auditing and allowlisting each package
that runs postinstall scripts) will silently skip all install-time lifecycle scripts on
`yarn install`.

mctl-portal is a Backstage monorepo that relies on several packages with postinstall scripts:
native Node.js bindings, Playwright browser downloads, and Backstage-internal setup scripts.
If the project upgrades to Yarn v4.14.0 without addressing this change, CI pipelines and
local developer builds will break with opaque, hard-to-diagnose errors (missing binaries,
absent browser executables) rather than a clear error message. A deliberate audit and an
explicit configuration decision — either a global opt-in or a per-package allowlist — must
be made before upgrading Yarn.

## User stories
- AS a platform engineer I WANT to know which packages in the mctl-portal monorepo rely on
  postinstall scripts SO THAT I can make an informed decision before upgrading Yarn to
  v4.14.0+.
- AS a developer running `yarn install` locally after a Yarn upgrade I WANT the build to
  succeed without manual intervention SO THAT my local environment matches CI without
  extra steps.
- AS a CI/CD maintainer I WANT `yarn install` in the CI pipeline to produce a fully
  functional build artifact SO THAT neither native bindings nor Playwright browsers are
  silently absent from the build.
- AS a security-conscious operator I WANT only explicitly approved packages to run install
  scripts SO THAT supply-chain risk from untrusted postinstall scripts is minimised.

## Acceptance criteria (EARS)
- WHEN `yarn install` is run after upgrading to Yarn v4.14.0+ THE SYSTEM SHALL execute
  postinstall scripts for all packages listed in the approved allowlist and skip all others.
- WHEN a new package with a postinstall script is added to `package.json` THE SYSTEM SHALL
  require an explicit allowlist entry before its install script runs, failing `yarn install`
  with a clear error message if no entry exists.
- WHILE CI runs `yarn install` on the v4.14.0+ lockfile THE SYSTEM SHALL produce working
  Playwright browser binaries in the expected cache location.
- WHILE CI runs `yarn install` THE SYSTEM SHALL compile or link all native Node.js addon
  packages (if any) that are present in the dependency tree.
- IF `enableScripts: false` is set globally and a package's install script is not
  allowlisted THE SYSTEM SHALL log a warning identifying the skipped package and its
  lifecycle script, rather than silently omitting it.
- WHEN the updated `.yarnrc.yml` configuration is committed THE SYSTEM SHALL be the
  single source of truth for which packages may run install scripts, with no undocumented
  manual steps required on developer machines or in CI.

## Out of scope
- Upgrading any Backstage or Node.js packages as part of this proposal.
- Removing or replacing Playwright in the e2e test suite.
- Migrating from Yarn Berry to npm or pnpm.
- Addressing the Yarn v4.14.1 EBADF flaw (only relevant on Node.js v24.15+; we run Node 22).
- Changes to ArgoCD manifests or production Kubernetes resources (install scripts are a
  build-time concern only).
