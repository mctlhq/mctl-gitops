# Design: playwright-test-locks-upgrade

## Current state
Per `context/architecture.md`, mctl-portal uses `playwright` for its e2e suite,
run as part of CI within the yarn workspaces monorepo (`packages/*`, `plugins/*`).
The suite currently runs without any inter-file/inter-worker locking mechanism;
tests that touch shared external state (e.g. scaffolder-created test services, a
shared Dex-authenticated session) rely on ad hoc conventions (unique naming,
sequential `describe` blocks, or manual `test.describe.serial`) to avoid
contention, which is a known source of intermittent CI flakiness.

## Proposed solution
Bump the `playwright` devDependency to v1.63.0 and adopt its new "Test Locks"
feature for the specific e2e specs known (or suspected) to touch shared external
resources. Concretely:
1. Bump `playwright` / `@playwright/test` in the workspace root `package.json`.
2. Audit existing e2e specs for cross-file/cross-worker shared-state usage
   (scaffolder-created services, shared auth sessions, shared k8s test namespaces).
3. Add named Test Lock annotations to the identified specs so Playwright serializes
   their execution instead of relying on ad hoc conventions.
4. Leave unaffected specs untouched — Test Locks are additive/opt-in, not a
   suite-wide rewrite.

This is a dev-tooling change confined to `devDependencies` and e2e spec files; no
production backend/frontend code is touched, and no Backstage plugin or
`@backstage/backend-defaults`-related concern applies here.

## Alternatives
- **Keep relying on `test.describe.serial` / manual conventions** — rejected as the
  status quo; it is exactly the source of flakiness this proposal aims to reduce,
  and does not scale as more contention-prone specs are added.
- **Restructure the e2e suite to avoid all shared state (fully isolated fixtures per
  test)** — considered as a more thorough fix, but rejected for this cycle as
  higher-effort (would require re-architecting scaffolder-created test fixtures and
  auth session handling); Test Locks give most of the benefit at a fraction of the
  effort. Could be revisited later if contention persists.
- **Defer the Playwright bump until a future release** — rejected; the bump itself
  is low-risk (dev-tooling only, patch/minor-level for our usage) and the Test Locks
  feature has immediate applicability to a known pain point (impact 2, effort 1 per
  the analyst's scoring).

## Platform impact
- **Migrations:** none. `devDependencies` bump plus e2e spec annotations; no
  runtime, schema, or config migration.
- **Backward compatibility:** fully backward compatible. CI pipeline invocation of
  Playwright (`playwright test` or equivalent) is unchanged; only specs explicitly
  annotated with Test Locks change behavior (serialized instead of parallel), which
  is the intended fix for contention, not a regression.
- **Resource impact (especially for `labs`):** not applicable. This is a
  dev-tooling/CI-only change with no production runtime footprint; it does not run
  in tenant `admins` production nor in tenant `labs` at all, so it does not consume
  or affect `labs` headroom.
- **Risks and mitigations:**
  - *Risk:* the version bump itself breaks the existing e2e config, reporter setup,
    or a used API surface (unrelated to Test Locks). *Mitigation:* run the full e2e
    suite in CI immediately after the bump, before adding any Test Lock
    annotations, to isolate "bump broke something" from "lock annotation broke
    something."
  - *Risk:* over-applying Test Locks serializes tests unnecessarily and slows CI.
    *Mitigation:* apply locks only to specs with confirmed or strongly suspected
    shared-state contention (per the audit step), not suite-wide.
  - *Risk:* release-date/version data from the researcher was flagged as
    possibly stale/cached. *Mitigation:* re-confirm the v1.63.0 changelog and
    version number directly against `https://github.com/microsoft/playwright/releases`
    before starting implementation (task 1).
